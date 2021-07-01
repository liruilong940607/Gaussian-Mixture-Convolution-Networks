#ifndef GPE_ONLY_FLOAT
#ifndef GPE_ONLY_2D
#include "convolution/implementation_backward.h"
#include <utility>

namespace convolution {
template std::pair<torch::Tensor, torch::Tensor> backward_impl_t<1, double, 3>(const torch::Tensor& grad, const ForwardOutput& forward_out, const Config& config);
} // namespace convolution
#endif // GPE_ONLY_2D
#endif // GPE_ONLY_FLOAT
