import unittest
import torch
import numpy as np
import scipy.signal

import gmc.mixture as gm
import gmc.modules as gmc
import gmc.mat_tools as mat_tools
import gmc.cpp.extensions.convolution.binding as cpp_convolution
import gmc.cpp.extensions.convolution_fitting.binding as cpp_convolution_fitting


class TestGM(unittest.TestCase):
    def test_convolutionOld(self):
        n_batches = 3
        n_layers_in = 4
        n_layers_out = 5
        gm_in = gm.generate_random_mixtures(n_batches, n_layers_in, 3, n_dims=2, pos_radius=1, cov_radius=0.25)
        conv_layer = gmc.ConvolutionOld(gmc.ConvolutionConfig(), n_layers_in=n_layers_in, n_layers_out=n_layers_out, n_dims=2, position_range=1, covariance_range=0.25, weight_sd=1)

        gm_out, gm_const = conv_layer(gm_in, torch.zeros(n_batches, n_layers_in))
        samples_per_unit = 50

        xv, yv = torch.meshgrid([torch.arange(-6, 6, 1 / samples_per_unit, dtype=torch.float),
                                 torch.arange(-6, 6, 1 / samples_per_unit, dtype=torch.float)])
        size = xv.size()[0]
        xes = torch.cat((xv.reshape(-1, 1), yv.reshape(-1, 1)), 1).view(1, 1, -1, 2)
        gm_in_samples = gm.evaluate(gm_in, xes).numpy()
        gm_out_samples = gm.evaluate(gm_out.detach(), xes).numpy()

        for l in range(n_layers_out):
            gm_kernel_samples = gm.evaluate(conv_layer.kernel(l).detach(), xes).view(n_layers_in, size, size).numpy()

            for b in range(n_batches):
                reference_solution = np.zeros((size, size))
                for k in range(n_layers_in):
                    kernel = gm_kernel_samples[k, :].reshape(size, size)
                    data = gm_in_samples[b, k, :].reshape(size, size)
                    reference_solution += scipy.signal.fftconvolve(data, kernel, 'same') / (samples_per_unit * samples_per_unit)
                    # plt.imshow(reference_solution); plt.colorbar(); plt.show()
                our_solution = gm_out_samples[b, l, :].reshape(size, size)
                reference_solution = reference_solution[1:, 1:]
                our_solution = our_solution[:-1, :-1]
                # plt.imshow(reference_solution); plt.colorbar(); plt.show()
                # plt.imshow(our_solution); plt.colorbar(); plt.show()

                max_l2_err = ((reference_solution - our_solution) ** 2).max()
                # plt.imshow((reference_solution - our_solution)); plt.colorbar(); plt.show();
                assert max_l2_err < 0.0000001

    def test_convolution(self):
        n_batches = 3
        n_layers_in = 4
        n_layers_out = 5
        gm_in = gm.generate_random_mixtures(n_batches, n_layers_in, 3, n_dims=2, pos_radius=1, cov_radius=0.25)
        conv_layer = gmc.Convolution(gmc.ConvolutionConfig(), n_layers_in=n_layers_in, n_layers_out=n_layers_out, n_dims=2, position_range=1, covariance_range=0.25, weight_sd=1)

        gm_out, gm_const = conv_layer(gm_in, torch.zeros(n_batches, n_layers_in))
        samples_per_unit = 50

        xv, yv = torch.meshgrid([torch.arange(-6, 6, 1 / samples_per_unit, dtype=torch.float),
                                 torch.arange(-6, 6, 1 / samples_per_unit, dtype=torch.float)])
        size = xv.size()[0]
        xes = torch.cat((xv.reshape(-1, 1), yv.reshape(-1, 1)), 1).view(1, 1, -1, 2)
        gm_in_samples = gm.evaluate(gm_in, xes).numpy()
        gm_out_samples = gm.evaluate(gm_out.detach(), xes).numpy()

        for l in range(n_layers_out):
            gm_kernel_samples = gm.evaluate(conv_layer.kernels()[l:l+1].detach(), xes).view(n_layers_in, size, size).numpy()

            for b in range(n_batches):
                reference_solution = np.zeros((size, size))
                for k in range(n_layers_in):
                    kernel = gm_kernel_samples[k, :].reshape(size, size)
                    data = gm_in_samples[b, k, :].reshape(size, size)
                    reference_solution += scipy.signal.fftconvolve(data, kernel, 'same') / (samples_per_unit * samples_per_unit)
                    # plt.imshow(reference_solution); plt.colorbar(); plt.show()
                our_solution = gm_out_samples[b, l, :].reshape(size, size)
                reference_solution = reference_solution[1:, 1:]
                our_solution = our_solution[:-1, :-1]
                # plt.imshow(reference_solution); plt.colorbar(); plt.show()
                # plt.imshow(our_solution); plt.colorbar(); plt.show()

                max_l2_err = ((reference_solution - our_solution) ** 2).max()
                # plt.imshow((reference_solution - our_solution)); plt.colorbar(); plt.show();
                assert max_l2_err < 0.0000001

    def test_convolution_fitting_without_fitting(self):
        print("test_convolution_fitting_gradcheck")
        n_batches = 1
        n_channels_in = 1
        n_components_in = 8
        n_kernel_gaussians = 1
        n_channels_out = 3
        for n_dims in (2, 3):
            print(f"n_dims={n_dims}")
            data = gm.generate_random_mixtures(n_batches, n_channels_in, n_components_in, n_dims=n_dims, pos_radius=1, cov_radius=0.25)
            kernels = gm.generate_random_mixtures(n_channels_out, n_channels_in, n_kernel_gaussians, n_dims=n_dims, pos_radius=1, cov_radius=0.25)

            reference = cpp_convolution.apply(data, kernels)
            # render.imshow(reference)

            n_fitting_components = n_channels_in * n_components_in * n_kernel_gaussians
            conv_fit_result = cpp_convolution_fitting.apply(data, kernels, n_fitting_components)

            # render.imshow(conv_fit_result)
            self.assertTrue((torch.sort(reference, dim=2)[0] - torch.sort(conv_fit_result, dim=2)[0]).abs().max().item() < 0.0001)

    def test_convolution_with_const(self):
        n_batches = 3
        n_layers_in = 4
        n_layers_out = 5
        gm_in_const = torch.randn(n_batches, n_layers_in) * 0.5
        gm_in = gm.generate_random_mixtures(n_batches, n_layers_in, 3, n_dims=2, pos_radius=1, cov_radius=0.25)
        conv_layer = gmc.Convolution(gmc.ConvolutionConfig(), n_layers_in=n_layers_in, n_layers_out=n_layers_out, n_dims=2, position_range=1, covariance_range=0.25, weight_sd=1)

        gm_out, gm_out_const = conv_layer(gm_in, gm_in_const)
        samples_per_unit = 100

        xv, yv = torch.meshgrid([torch.arange(-12, 12, 1 / samples_per_unit, dtype=torch.float),
                                 torch.arange(-12, 12, 1 / samples_per_unit, dtype=torch.float)])
        size = xv.size()[0]
        xes = torch.cat((xv.reshape(-1, 1), yv.reshape(-1, 1)), 1).view(1, 1, -1, 2)
        gm_in_samples = (gm.evaluate(gm_in, xes) + gm_in_const.unsqueeze(-1)).numpy()
        gm_out_samples = (gm.evaluate(gm_out, xes) + gm_out_const.unsqueeze(-1)).detach().numpy()

        for l in range(n_layers_out):
            gm_kernel_samples = gm.evaluate(conv_layer.kernels()[l:l+1].detach(), xes).view(n_layers_in, size, size).numpy()

            for b in range(n_batches):
                reference_solution = np.zeros((size, size))
                for k in range(n_layers_in):
                    kernel = gm_kernel_samples[k, :].reshape(size, size)
                    data = gm_in_samples[b, k, :].reshape(size, size)
                    reference_solution += scipy.signal.fftconvolve(data, kernel, 'same') / (samples_per_unit * samples_per_unit)
                    # plt.imshow(reference_solution); plt.colorbar(); plt.show()
                # the reference solution has a border, because the constant is infinite in the gm representation but not in the discrete representation
                # we cut out the centre and compare only that
                our_solution = gm_out_samples[b, l, :].reshape(size, size)
                reference_solution = reference_solution[1:, 1:]
                our_solution = our_solution[:-1, :-1]
                reference_solution = reference_solution[500:-500, 500:-500]
                our_solution = our_solution[500:-500, 500:-500]
                # plt.imshow(reference_solution); plt.colorbar(); plt.show()
                # plt.imshow(our_solution); plt.colorbar(); plt.show()

                max_l2_err = ((reference_solution - our_solution) ** 2).max()
                # plt.imshow((reference_solution - our_solution)); plt.colorbar(); plt.show();
                assert max_l2_err < 0.0000001
                # plt.show()

    def test_cov_scale_norm(self):
        norm = gmc.CovScaleNorm(n_layers=1, batch_norm=False)

        m = torch.tensor([1, 1, 1, 1, 0, 0, 1], dtype=torch.float).view(1, 1, 1, -1)
        mp_ref = torch.tensor([1, 1, 1, 1, 0, 0, 1], dtype=torch.float).view(1, 1, 1, -1)
        mp, _ = norm((m, None))
        self.assertLess((mp_ref - mp).abs().mean().item(), 0.000001)

        m = torch.tensor([1, 1, 1, 4, 0, 0, 4], dtype=torch.float).view(1, 1, 1, -1)
        mp, _ = norm((m, None))
        self.assertAlmostEqual(mat_tools.trace(gm.covariances(mp)).item(), 2, places=5)

        m = torch.tensor([1, 1, 1, 4, 0, 0, 9], dtype=torch.float).view(1, 1, 1, -1)
        mp, _ = norm((m, None))
        self.assertAlmostEqual(mat_tools.trace(gm.covariances(mp)).item(), 2, places=5)

        norm = gmc.CovScaleNorm(n_layers=10, batch_norm=False)
        m = gm.generate_random_mixtures(20, 10, 30, 3, pos_radius=15, cov_radius=30)
        mp, _ = norm((m, None))
        self.assertAlmostEqual(mat_tools.trace(gm.covariances(mp)).mean().item(), 3, places=5)


if __name__ == '__main__':
    unittest.main()
