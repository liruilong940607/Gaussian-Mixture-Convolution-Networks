import math

import torch
from pygments.lexer import include
from torch import Tensor
import numpy as np
import matplotlib.pyplot as plt

import mat_tools


class Mixture:
    # data: first dimension: batch, second dimension: component, third and fourth(?) dimension: data
    def __init__(self, weights: Tensor, positions: Tensor, covariances: Tensor) -> None:
        assert len(weights.size()) == 2
        assert len(positions.size()) == 3
        assert len(covariances.size()) == 4

        self.weights = weights
        self.positions = positions
        self.covariances = covariances

        assert self.n_components() == weights.size()[1]
        assert self.n_components() == positions.size()[1]
        assert self.n_components() == covariances.size()[1]
        assert covariances.size()[2] == self.n_dimensions()
        assert covariances.size()[3] == self.n_dimensions()
        assert torch.all(covariances.det() > 0)

        self.inverted_covariances = covariances.inverse()

    def device(self):
        return self.weights.device

    def n_components(self):
        return self.weights.size()[1]

    def n_batches(self):
        return self.weights.size()[0]

    def n_dimensions(self):
        return self.positions.size()[2]

    def evaluate_few_xes_component_wise(self, xes: Tensor) -> Tensor:
        n_batches = self.n_batches()
        n_dims = self.n_dimensions()
        n_comps = self.n_components()
        # xes: first dim: list, second dim; x/y

        # 1. dim: batches (from mixture), 2. component, 3. xes, 4.+: vector / matrix components
        xes = xes.view(1, 1, -1, n_dims)
        positions = self.positions.view(n_batches, n_comps, 1, n_dims)
        values = xes - positions

        # x^t A x -> quadratic form
        x_t = values.view(n_batches, n_comps, -1, 1, n_dims)
        x = values.view(n_batches, n_comps, -1, n_dims, 1)
        A = self.inverted_covariances.view(n_batches, n_comps, 1, n_dims, n_dims)
        values = -0.5 * x_t @ A @ x
        values = values.view(n_batches, n_comps, -1)
        values = self.weights.view(n_batches, n_comps, 1) * torch.exp(values)
        return values.view(n_batches, n_comps, -1)

    def evaluate_few_xes(self, xes: Tensor) -> Tensor:
        return self.evaluate_few_xes_component_wise(xes).sum(1)

    def evaluate_component_many_xes(self, xes: Tensor, component: int) -> Tensor:
        n_batches = self.n_batches()
        n_dims = self.n_dimensions()
        assert xes.size()[1] == n_dims
        assert component < self.n_components()

        weights = self.weights[:, component].view(-1, 1)
        positions = self.positions[:, component, :]
        inverted_covs = self.inverted_covariances[:, component, :, :]

        # first dimension: batch (from mixture), second: sampling (xes), third: data
        v = xes.view(1, -1, n_dims) - positions.view(-1, 1, n_dims)
        # first dimension: batch (from mixture), second: sampling (xes), third and fourth: matrix data
        inverted_covs = inverted_covs.view(-1, 1, n_dims, n_dims)

        v = -0.5 * v.view(n_batches, -1, 1, n_dims) @ inverted_covs @ v.view(n_batches, -1, n_dims, 1)
        v = v.view(n_batches, -1)
        v = weights * torch.exp(v)
        assert not torch.isnan(v).any()
        assert not torch.isinf(v).any()
        return v

    def evaluate_many_xes(self, xes: Tensor) -> Tensor:
        #todo: implement batched
        assert self.n_batches() == 1
        values = torch.zeros(xes.size()[0], dtype=torch.float32, device=xes.device)
        for i in range(self.n_components()):
            # todo: adding many components like this probably makes the gradient graph and therefore memory explode
            values += self.evaluate_component_many_xes(xes, i).view(-1)
        return values
    
    def max_component_many_xes(self, xes: Tensor) -> Tensor:
        #todo: implement batched
        assert self.n_batches() == 1
        selected = torch.zeros(xes.size()[1], dtype=torch.long)
        values = self.evaluate_component_many_xes(xes, 0)
        for i in range(self.n_components()):
            component_values = self.evaluate_component_many_xes(xes, i).view(-1)
            mask = component_values > values
            selected[mask] = i
            values[mask] = component_values[mask]
        
        return selected
            
    def debug_show(self, x_low: float = -22, y_low: float = -22, x_high: float = 22, y_high: float = 22, step: float = 0.1) -> Tensor:
        #todo: implement batched
        assert self.n_batches() == 1
        xv, yv = torch.meshgrid([torch.arange(x_low, x_high, step, dtype=torch.float, device=self.weights.device),
                                 torch.arange(y_low, y_high, step, dtype=torch.float, device=self.weights.device)])
        xes = torch.cat((xv.reshape(1, -1), yv.reshape(1, -1)), 0)
        values = self.evaluate_many_xes(xes).detach()
        image = values.view(xv.size()[0], xv.size()[1]).cpu().numpy()
        plt.imshow(image)
        plt.colorbar()
        plt.show()
        return image

    def cuda(self):
        return Mixture(self.weights.cuda(), self.positions.cuda(), self.covariances.cuda())

    def cpu(self):
        return Mixture(self.weights.cpu(), self.positions.cpu(), self.covariances.cpu())

    def batch(self, batch_id: int):
        n_dims = self.n_dimensions()
        return Mixture(self.weights[batch_id, :].view(1, -1),
                       self.positions[batch_id, :, :].view(1, -1, n_dims),
                       self.positions[batch_id, :, :, :].view(1, -1, n_dims, n_dims))

    def detach(self):
        detached_mixture = generate_null_mixture(1, self.dimensions, device=self.device())
        detached_mixture.weights = self.weights.detach()
        detached_mixture.positions = self.positions.detach()
        detached_mixture.covariances = self.covariances.detach()
        detached_mixture.inverted_covariances = self.inverted_covariances.detach()
        return detached_mixture

    def save(self, file_name: str):
        dict = {
            "type": "gm.Mixture",
            "version": 2,
            "weights": self.weights,
            "positions": self.positions,
            "covariances": self.covariances
        }
        torch.save(dict, "/home/madam/temp/prototype/" + file_name)

    @classmethod
    def load(cls, file_name: str):
        dict = torch.load("/home/madam/temp/prototype/" + file_name)
        assert dict["type"] == "gm.Mixture"
        assert dict["version"] == 2
        return Mixture(dict["weights"], dict["positions"], dict["covariances"])


class ReLUandBias:
    # todo batched
    def __init__(self, mixture: Mixture, bias: Tensor):
        assert bias >= 0
        self.mixture = mixture
        self.bias = bias

    def evaluate_few_xes(self, positions: Tensor):
        values = self.mixture.evaluate_few_xes(positions) - self.bias
        return torch.max(values, torch.tensor([0.0001], dtype=torch.float32, device=self.mixture.device()))

    def debug_show(self, x_low: float = -22, y_low: float = -22, x_high: float = 22, y_high: float = 22, step: float = 0.1) -> Tensor:
        m = self.mixture.detach()
        xv, yv = torch.meshgrid([torch.arange(x_low, x_high, step, dtype=torch.float, device=m.device()),
                                 torch.arange(y_low, y_high, step, dtype=torch.float, device=m.device())])
        xes = torch.cat((xv.reshape(1, -1), yv.reshape(1, -1)), 0)
        values = m.evaluate_many_xes(xes)
        values -= self.bias.detach()
        values[values < 0] = 0
        image = values.view(xv.size()[0], xv.size()[1]).cpu().numpy()
        plt.imshow(image)
        plt.colorbar()
        plt.show()
        return image

    def device(self):
        return self.mixture.device()


def single_batch_mixture(weights: Tensor, positions: Tensor, covariances: Tensor):
    n_dims = positions.size()[1]
    return Mixture(weights.view(1, -1), positions.view(1, -1, n_dims), covariances.view(1, -1, n_dims, n_dims))


# we will need to work on the initialisation. it's unlikely this simple one will work.
def generate_random_mixtures(n_batch: int, n_components: int, n_dims: int,
                             pos_radius: float = 10,
                             cov_radius: float = 10,
                             factor_min: float = -1,
                             factor_max: float = 1,
                             device: torch.device = 'cpu') -> Mixture:
    assert n_dims == 2 or n_dims == 3
    assert factor_min < factor_max
    assert n_components > 0
    assert n_batch > 0

    weights = torch.rand(n_batch, n_components, dtype=torch.float32, device=device) * (factor_max - factor_min) + factor_min
    positions = torch.rand(n_batch, n_components, n_dims, dtype=torch.float32, device=device) * 2 * pos_radius - pos_radius
    covs = mat_tools.gen_random_positive_definite((n_batch, n_components, n_dims, n_dims), device=device) * cov_radius

    return Mixture(weights, positions, covs)


# todo: this function is a mess
def generate_null_mixture(n_batch: int, n_components: int, n_dims: int, device: torch.device = 'cpu') -> Mixture:
    m = generate_random_mixtures(n_batch, n_components, n_dims, device=device)
    m.weights *= 0
    m.positions *= 0
    m.covariances *= 0
    m.inverted_covariances *= 0
    return m


def _polynomMulRepeat(A: Tensor, B: Tensor) -> (Tensor, Tensor):
    # todo: port to batched
    if len(A.size()) == 2:
        A_n = A.size()[1]
        B_n = B.size()[1]
        return (A.repeat(1, B_n), B.repeat_interleave(A_n, 1))
    else:
        A_n = A.size()[0]
        B_n = B.size()[0]
        return (A.repeat(B_n), B.repeat_interleave(A_n))


def convolve(m1: Mixture, m2: Mixture) -> Mixture:
    # todo: port to batched
    assert m1.dimensions == m2.dimensions
    m1_f, m2_f = _polynomMulRepeat(m1.weights, m2.weights)
    m1_p, m2_p = _polynomMulRepeat(m1.positions, m2.positions)
    m1_c, m2_c = _polynomMulRepeat(m1.covariances, m2.covariances)

    positions = m1_p + m2_p
    covariances = m1_c + m2_c
    detc1tc2 = mat_tools.triangle_det(m1_c) * mat_tools.triangle_det(m2_c)
    detc1pc2 = mat_tools.triangle_det(covariances)
    factors = math.pow(math.sqrt(2 * math.pi), m1.dimensions) * m1_f * m2_f * torch.sqrt(detc1tc2) / torch.sqrt(detc1pc2)
    return Mixture(factors, positions, covariances)
