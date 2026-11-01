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

[Experiment, paraphrase; the table of results is not reproduced in this variant.] Data: 480 binary 16x16 images; twelve examples of each digit were drawn by hand on a
16x13 bitmap and each shifted horizontally into four positions; 320 used for training, 160 for testing. Five
networks of increasing constraint were trained with back-propagation, from a single layer with no hidden units
through fully connected and locally connected hidden layers to hierarchies of constrained feature detectors.

The conclusion: single layer networks generalized poorly although the problem is linearly separable; the more a
network's architecture was constrained, the better it generalized; the network with the most connections and the
fewest free parameters generalized best. Where units of a layer are constrained to detect the same feature at
different positions, the weight changes are summed (as in the T-C experiment of Rumelhart, Hinton and Williams),
with a separate bias per unit.
