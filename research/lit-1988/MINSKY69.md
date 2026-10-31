# Perceptrons

Date: 1969
Kind: paraphrase
Source: M. Minsky and S. Papert, MIT Press, 1969

[Paraphrase, not verbatim.] Minsky and Papert analysed what a single-layer perceptron (adjustable weights only on
the last layer, with predicate units of bounded "order" below it) can compute. Using group-invariance arguments
they proved that certain predicates cannot be computed by any perceptron whose predicates look at a bounded number
of retina points: parity requires predicates of order equal to the number of points, and connectedness of a figure
cannot be decided by diameter-limited or order-limited perceptrons. They noted that these limits apply to the
single adjustable layer; multilayer networks could in principle compute such predicates, but, in their view, no
learning procedure for multilayer machines was known and they were not optimistic that an interesting one would
be found. The book is often credited with ending most research funding for perceptron-style learning machines in
the 1970s.
