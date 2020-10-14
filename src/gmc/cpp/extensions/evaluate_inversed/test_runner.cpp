#include <iostream>
#include <string>

#include <QApplication>
#include <QImage>
#include <QLabel>
#include <QScrollArea>

#include <torch/torch.h>
#include <torch/script.h>

#include <cuda_runtime.h>

#include "common.h"
#include "mixture.h"

#include "parallel_binding.h"

std::tuple<torch::Tensor, torch::Tensor, torch::Tensor> cuda_bvh_forward(const torch::Tensor& mixture, const torch::Tensor& xes);

torch::Tensor cuda_bvh_forward_wrapper(const torch::Tensor& mixture, const torch::Tensor& xes) {
    torch::Tensor sum, nodes, aabbs;
    std::tie(sum, nodes, aabbs) = cuda_bvh_forward(mixture, xes);
    return sum;
}

auto eval_function(const torch::Tensor& tensor) {
    GPE_UNUSED(tensor)
    return &cuda_bvh_forward_wrapper;
//    return &parallel_forward;
//    return tensor.is_cuda() ? &cuda_bvh_forward_wrapper : &parallel_forward;
}


auto eval_function_backward(const torch::Tensor& tensor) {
    GPE_UNUSED(tensor)
    return &parallel_backward;
//    return tensor.is_cuda() ? &cuda_bvh_forward_wrapper : &parallel_forward;
}

constexpr uint N_BATCHES = 1;
constexpr uint N_CONVOLUTION_LAYERS = 3;
constexpr uint LIMIT_N_BATCH = 100;
constexpr bool USE_CUDA = true;
constexpr bool BACKWARD = false;
constexpr bool RENDER = true;

void show(torch::Tensor mixture, const int resolution, const int n_batch_limit) {
    using namespace torch::indexing;
    const auto n_batch = std::min(gpe::n_batch(mixture), n_batch_limit);
    mixture = mixture.index({Slice(None, n_batch)});
    const auto n_layers = gpe::n_layers(mixture);

    const auto weights = gpe::weights(mixture);
    const auto positions = gpe::positions(mixture);
    const auto invCovs = gpe::covariances(mixture).inverse().transpose(-1, -2);
    mixture = gpe::pack_mixture(weights, positions, invCovs.contiguous());

    const auto minPos = positions.min().item().toFloat() - 1.1f;
    const auto maxPos = positions.max().item().toFloat() + 1.1f;

    const auto mesh = torch::meshgrid({torch::arange(minPos, maxPos, 1.00001f * (maxPos - minPos) / float(resolution), mixture.device()),
                                       torch::arange(minPos, maxPos, 1.00001f * (maxPos - minPos) / float(resolution), mixture.device())});
    auto xv = mesh[0];
    auto yv = mesh[1];
    auto xes = torch::cat({xv.reshape({-1, 1}), yv.reshape({-1, 1})}, 1).view({1, 1, -1, 2});
    std::cout << "xes.sizes() = " << xes.sizes() << std::endl;

    cudaDeviceSynchronize();
    auto start = std::chrono::steady_clock::now();
    auto rendering = eval_function(mixture)(mixture, xes).cpu().view({n_batch, n_layers, resolution, resolution});
    cudaDeviceSynchronize();
    auto end = std::chrono::steady_clock::now();
    std::cout << "elapsed time (rendering): " << std::chrono::duration_cast<std::chrono::milliseconds>(end-start).count() << "ms\n";
    std::cout << "rendering.sizes() = " << rendering.sizes()
              << ", min=" << rendering.min().item<float>()
              << ", max=" << rendering.max().item<float>() << std::endl;
    rendering -= rendering.min();
    rendering /= rendering.max();
    rendering *= 255;
    rendering = rendering.to(torch::ScalarType::Char);
    rendering = rendering.transpose(2, 3).transpose(1, 2).contiguous();
    QImage qRendering(reinterpret_cast<uchar*>(rendering.data_ptr()), resolution * n_layers, resolution * n_batch, QImage::Format_Grayscale8);
    QLabel* myLabel = new QLabel();
    myLabel->setPixmap(QPixmap::fromImage(qRendering));

    QScrollArea* scrollarea = new QScrollArea();
    scrollarea->setWidget(myLabel);
    scrollarea->show();
}

int main(int argc, char *argv[]) {
    using namespace torch::indexing;
    QApplication a(argc, argv);

    cudaDeviceSynchronize();
    for (uint i = 0; i < N_BATCHES; ++i) {
        torch::jit::script::Module container = torch::jit::load("/home/madam/Documents/work/tuw/gmc_net/data/fitting_input/fitting_input_batch" + std::to_string(i) + ".pt");
        auto list = container.attributes();

        for (uint i = 0; i < N_CONVOLUTION_LAYERS; i++) {
            torch::Tensor mixture = container.attr(std::to_string(i)).toTensor();//.index({Slice(0, 1), Slice(0, 1), Slice(0, 5), Slice()});
//            auto mixture = torch::tensor({{0.02f, 0.f, 0.f, 1.01f, 1.f, 1.f, 1.0f},
//                                          {0.02f, 5.f, 5.f, 1.01f, 0.5f, 0.5f, 4.0f}}).view({1, 1, 2, 7});
            if (USE_CUDA)
                mixture = mixture.cuda();
            std::cout << "layer " << i << ": " << mixture.sizes() << " device: " << mixture.device() << std::endl;
            if (RENDER)
                show(mixture, 128, LIMIT_N_BATCH);

            const auto weights = gpe::weights(mixture);
            torch::Tensor positions = gpe::positions(mixture);
            const auto invCovs = gpe::covariances(mixture).inverse().transpose(-1, -2);
            mixture = gpe::pack_mixture(weights, positions, invCovs.contiguous()).clone().contiguous();
            cudaDeviceSynchronize();

            auto start = std::chrono::high_resolution_clock::now();
            auto eval_values = eval_function(mixture)(mixture, positions.contiguous());
            cudaDeviceSynchronize();
            auto end = std::chrono::high_resolution_clock::now();
            std::cout << "elapsed time (forward): " << std::chrono::duration_cast<std::chrono::milliseconds>(end-start).count() << "ms\n";

            if (BACKWARD) {
                torch::Tensor positions_clone = gpe::positions(mixture).clone();
                auto grad_out = torch::rand_like(eval_values);

                cudaDeviceSynchronize();
                auto start = std::chrono::high_resolution_clock::now();
                auto grads = eval_function_backward(mixture)(grad_out, mixture, positions_clone, true, true);
                cudaDeviceSynchronize();
                auto end = std::chrono::high_resolution_clock::now();
                std::cout << "elapsed time (backward): " << std::chrono::duration_cast<std::chrono::milliseconds>(end-start).count() << "ms\n";

            }
        }
    }

    std::cout << "DONE" << std::endl;
    if (RENDER)
        return a.exec();
    else
        return 0;
}
