# Learning internal representations by error propagation

Date: 1986
Kind: paraphrase
Source: D. E. Rumelhart, G. E. Hinton and R. J. Williams, in Parallel Distributed Processing, vol. 1, ch. 8, MIT Press 1986

[Paraphrase, not verbatim; see RHW86-TC for the verbatim weight-constraint passage.] The chapter presents the
generalized delta rule for networks of units with a smooth (logistic) activation function arranged in layers with
hidden units. For an input pattern, the activities are computed forward layer by layer; the error (sum of squared
differences between actual and target outputs) is then propagated backward: the error signal of a hidden unit is
the weighted sum of the error signals of the units it feeds, multiplied by the derivative of its activation
function, and each weight is changed in proportion to the error signal of the receiving unit times the activity
of the sending unit. The procedure is gradient descent on the total error. The authors demonstrate it on XOR,
parity, encoding, symmetry, negation, the T-C discrimination problem and other tasks, and report that the hidden
units develop useful internal representations. They note that the procedure can be slow and that it is not
guaranteed to find a global minimum, but that local minima were rarely a problem in their experiments.
