#include "bvh_mhem_fit/implementation_forward.h"

namespace bvh_mhem_fit {
#ifndef GPE_LIMIT_N_REDUCTION
template ForwardOutput forward_impl_t<16, float, 3>(torch::Tensor mixture, const BvhMhemFitConfig& config);
#endif
} // namespace bvh_mhem_fit
