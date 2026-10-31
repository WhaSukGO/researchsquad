# A theoretical framework for back-propagation

Date: 1988
Kind: paraphrase
Source: Y. Le Cun, Proceedings of the 1988 Connectionist Models Summer School (Touretzky, Hinton, Sejnowski eds.), Morgan Kaufmann, pp. 21-28

[Paraphrase, not verbatim.] The paper derives back-propagation from a Lagrangian formulation: the forward
equations of the network are treated as constraints, multiplied by Lagrange multipliers and added to the output
cost; stationarity of the resulting functional with respect to the unit states yields the backward (adjoint)
equations whose solutions are the multipliers, and stationarity with respect to the weights yields the gradient.
This shows that back-propagation is the discrete-time analogue of the adjoint-state method of optimal control,
extends it to networks with arbitrary feed-forward or recurrent topologies, to units with non-differentiable or
constrained states, and to weight constraints: when several connections are constrained to share one weight, the
gradient with respect to the shared weight is the sum of the gradients with respect to each of the tied
connections. The author also discusses second-order (Newton-like) variants using a diagonal approximation of the
Hessian computed by a backward pass.
