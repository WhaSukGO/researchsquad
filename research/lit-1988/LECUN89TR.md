# Generalization and network design strategies

Date: 1988-06
Kind: excerpt
Source: Y. Le Cun, Technical Report CRG-TR-89-4, Department of Computer Science, University of Toronto (experiments performed during the 1987-88 postdoctoral year; report dated June 1989); shortened version in Connectionism in Perspective, Elsevier 1989

[Abstract, verbatim from the announcement.] "An interesting property of connectionist systems is their ability to
learn from examples. Although most recent work in the field concentrates on reducing learning times, the most
important feature of a learning machine is its generalization performance. It is usually accepted that good
generalization performance on real-world problems cannot be achieved unless some a priori knowledge about the
task is built into the system. Back-propagation networks provide a way of specifying such knowledge by imposing
constraints both on the architecture of the network and on its weights. In general, such constraints can be
considered as particular transformations of the parameter space. Building a constrained network for image
recognition appears to be a feasible task. We describe a small handwritten digit recognition problem and show
that, even though the problem is linearly separable, single layer networks exhibit poor generalization
performance. Multilayer constrained networks perform very well on this task when organized in a hierarchical
structure with shift invariant feature detectors. These results confirm the idea that minimizing the number of
free parameters in the network enhances generalization. We also briefly describe a second order variant of
back-propagation using a diagonal approximation of the Hessian."

[Experiment, paraphrase.] Data: 480 binary 16x16 images; twelve examples of each digit were drawn by hand on a
16x13 bitmap and each shifted horizontally into four positions; 320 used for training, 160 for testing. Five
networks trained with back-propagation:

| net | architecture | connections | independent parameters | test correct |
|---|---|---|---|---|
| Net-1 | 16x16 -> 10, fully connected, no hidden layer | 2,570 | 2,570 | 80.0% |
| Net-2 | 16x16 -> 12 -> 10, fully connected | 3,214 | 3,214 | 87.0% |
| Net-3 | two locally connected hidden layers, 3x3 receptive fields, stride 2, no sharing | 1,226 | 1,226 | 88.5% |
| Net-4 | one layer of shared-weight feature maps (2 maps, 8x8), then a locally connected layer | 2,266 | 1,132 | 94.0% |
| Net-5 | two layers of shared-weight feature maps (2 maps 8x8, then 4 maps 4x4) | 5,194 | 1,060 | 98.4% |

In Net-4 and Net-5 the units of a feature map are constrained to have identical weight vectors (the weight
changes are summed, as in the T-C experiment of Rumelhart, Hinton and Williams), with a separate bias per unit.
Net-5 has the most connections and the fewest free parameters and generalizes best.
