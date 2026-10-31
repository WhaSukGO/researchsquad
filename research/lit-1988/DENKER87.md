# Large automatic learning, rule extraction, and generalization

Date: 1987
Kind: paraphrase
Source: J. Denker, D. Schwartz, B. Wittner, S. Solla, R. Howard, L. Jackel and J. Hopfield, Complex Systems 1:877-922, 1987

[Paraphrase, not verbatim.] Written at AT&T Bell Laboratories, Holmdel, this paper defines memorization,
generalization and rule extraction precisely for networks that learn from examples. A network that can implement
very many functions of its inputs can fit any training set but gives essentially random answers on inputs it has
not seen; a network whose architecture restricts the set of implementable functions, so that few of them are
consistent with the examples, can be expected to generalize. The authors quantify this with an entropy-like
measure of the number of functions the network can realize, and argue that good generalization requires either
many examples or strong prior constraints built into the architecture, and that the number of adjustable
parameters should be kept small relative to the number of examples. They also discuss active learning (choosing
informative examples) and the role of hardware implementations.
