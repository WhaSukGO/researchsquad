# Optimal perceptual inference

Date: 1983
Kind: paraphrase
Source: G. E. Hinton and T. J. Sejnowski, Proc. IEEE Conf. on Computer Vision and Pattern Recognition, 1983

[Paraphrase, not verbatim.] Hinton and Sejnowski treated perceptual interpretation as finding the most probable
global interpretation given noisy local evidence, and proposed a network of stochastic binary units that performs
this inference. Units update probabilistically according to the energy difference between their two states; with
a temperature parameter that is lowered gradually (simulated annealing), the network settles toward low-energy
interpretations and escapes shallow local minima that deterministic relaxation gets stuck in. Importantly for
learning, they sketched how the weights of such a network, including weights to hidden units that represent
features not present in the input, could be adjusted from examples so that the network's equilibrium
distribution matches the environment; this became the Boltzmann machine learning procedure. The paper is one of
the first to describe learning in networks with hidden units.
