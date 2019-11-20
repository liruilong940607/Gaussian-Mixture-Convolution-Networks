import typing
import time

import torch
import torch.distributions.categorical
import torch.optim as optim
import torch.nn as nn
from torch import Tensor

import gm
from fitGmNet import Net as FitGmNet

DIMS = 2
N_SAMPLES = 50 * 50
N_INPUT_GAUSSIANS = 10
N_OUTPUT_GAUSSIANS = 10
COVARIANCE_MIN = 0.01
COV_DECOMPOSITION = True

BATCH_SIZE = 200
LEARNING_RATE = 0.001
N_BATCHES = 5000000

assert DIMS == 2 or DIMS == 3
assert N_SAMPLES > 0
assert N_INPUT_GAUSSIANS >= N_OUTPUT_GAUSSIANS
assert COVARIANCE_MIN > 0


def generate_random_ReLUandBias(device: torch.device = 'cpu'):
    # if N_INPUT_GAUSSIANS == 100:
    #     random_m = gm.generate_random_mixtures(10, DIMS, pos_radius=1, cov_radius=0.25, factor_min=0, factor_max=10, device=net.device())
    #     random_kernel = gm.generate_random_mixtures(10, DIMS, pos_radius=0.08, cov_radius=0.04, device=net.device())
    #     # todo: print and check factors of convolved gm
    #     input_gm_after_activation = gm.ConvolutionLayer(gm.convolve(random_m, random_kernel),
    #                                                     torch.rand(1, dtype=torch.float32, device=net.device()) * 1)
    # else:
    input_gm_after_activation = gm.MixtureReLUandBias(gm.generate_random_mixtures(BATCH_SIZE, N_INPUT_GAUSSIANS, DIMS,
                                                                                  pos_radius=1, cov_radius=0.25,
                                                                                  factor_min=0, factor_max=1, device=device),
                                                      torch.zeros(BATCH_SIZE, dtype=torch.float32, device=device))
    # distribution = torch.distributions.categorical.Categorical(torch.ones(N_INPUT_GAUSSIANS, device=device))
    # # zero some input gaussians so we can learn a one to one mapping
    # good_indices = distribution.sample(torch.Size([N_BATCHES, N_OUTPUT_GAUSSIANS]))
    # bool_vector = torch.ones_like(input_gm_after_activation.mixture.weights, dtype=torch.bool)
    # bool_vector[good_indices] = False
    # input_gm_after_activation.mixture.weights[bool_vector] = 0
    return input_gm_after_activation


def test_dl_fitting(g_layer_sizes: typing.List,
                    fully_layer_sizes: typing.List,
                    use_cuda: bool = True,
                    cov_decomposition: bool = True,
                    testing_mode: bool = True):
    net = FitGmNet(g_layer_sizes, fully_layer_sizes, N_INPUT_GAUSSIANS, N_OUTPUT_GAUSSIANS, DIMS, cov_decomposition=cov_decomposition)
    net.load()

    if use_cuda:
        net = net.cuda()
    else:
        net = net.cpu()

    for parameter in net.parameters():
        print(f"parameter: {parameter.shape}")

    criterion = nn.MSELoss()
    optimiser = optim.Adam(net.parameters(), lr=LEARNING_RATE)
    print(net)

    running_loss_avg = 0
    for i in range(1 if testing_mode else N_BATCHES):
        batch_start_time = time.perf_counter()
        optimiser.zero_grad()

        input_relu_of_gm_p_bias = generate_random_ReLUandBias(device=net.device())
        sampling_positions = torch.rand((BATCH_SIZE, N_SAMPLES, DIMS), dtype=torch.float32, device=net.device()) * 3 - 1.5
        target_sampling_values = input_relu_of_gm_p_bias.evaluate_few_xes(sampling_positions)

        network_start_time = time.perf_counter()
        output_gm: gm.Mixture = net(input_relu_of_gm_p_bias)
        network_time = time.perf_counter() - network_start_time

        eval_start_time = time.perf_counter()
        output_gm_sampling_values = output_gm.evaluate_few_xes(sampling_positions)
        loss = criterion(output_gm_sampling_values, target_sampling_values)
        eval_time = time.perf_counter() - eval_start_time

        backward_start_time = time.perf_counter()
        loss.backward()
        backward_time = time.perf_counter() - backward_start_time

        if testing_mode:
            for j in range(BATCH_SIZE):
                input_relu_of_gm_p_bias.debug_show(j, -2, -2, 2, 2, 0.05)
                output_gm.debug_show(j, -2, -2, 2, 2, 0.05)
                input("Press enter to continue")
        if not testing_mode:
            optimiser.step()

        grad_norm_min = 1100000
        grad_norm_sum = 0
        grad_norm_max = 0
        grad_norm_cnt = 0
        running_loss_avg = running_loss_avg * 0.98 + loss * 0.02
        for p in list(filter(lambda p: p.grad is not None, net.parameters())):
            grad_norm = p.grad.data.norm(2).item()
            grad_norm_min = grad_norm if grad_norm < grad_norm_min else grad_norm_min
            grad_norm_max = grad_norm if grad_norm > grad_norm_max else grad_norm_max
            grad_norm_sum += grad_norm
            grad_norm_cnt += 1

        info = (f"iteration i = {i}: "
                f"batch loss {loss:.4f} (avg50: {running_loss_avg:.5f}), "
                f"batch time = {time.perf_counter() - batch_start_time :.2f}s, "
                f"size = {BATCH_SIZE}, "
                f"(forward: {network_time :.2f}s ({network_time / BATCH_SIZE :.4f}s), eval: {eval_time :.3f}s, backward: {backward_time :.4f}s) "
                f"grad_norm: {grad_norm_min :.6f}/{grad_norm_sum / grad_norm_cnt :.6f}/{grad_norm_max :.6f}")
        print(info)
        if not testing_mode and i % 50 == 0:
            net.save()
            f = open("/home/madam/temp/prototype/" + net.name + "_loss", "w")
            f.write(info)
            f.close()

    # target, input_ = draw_random_samples(10, WIDTH, HEIGHT)
    # output = net(input_)
    # print(f"target={target}")
    # print(f"output={output}")
    # print(f"diff={output - target}")




test_dl_fitting(g_layer_sizes=[64, 128, 128, 512, 512 * N_OUTPUT_GAUSSIANS], fully_layer_sizes=[512, 256, 128, 64, 32],
                use_cuda=False, cov_decomposition=False)
# test_dl_fitting(g_layer_sizes=[64, 128, 128, 512, 512 * N_OUTPUT_GAUSSIANS], fully_layer_sizes=[512, 256, 128, 64, 32])
