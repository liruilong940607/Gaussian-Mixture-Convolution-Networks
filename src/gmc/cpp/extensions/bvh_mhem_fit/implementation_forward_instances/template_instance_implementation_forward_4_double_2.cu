#ifndef GPE_ONLY_FLOAT
#include "bvh_mhem_fit/implementation_forward.h"

namespace bvh_mhem_fit {
template ForwardOutput forward_impl_t<4, double, 2>(torch::Tensor mixture, const Config& config);
} // namespace bvh_mhem_fit
#endif // GPE_ONLY_FLOAT
