# Learning internal representations by error propagation, section 'The T-C problem' (weight constraint passage)

Date: 1986
Kind: excerpt
Source: D. E. Rumelhart, G. E. Hinton and R. J. Williams, in Parallel Distributed Processing, vol. 1, ch. 8, pp. 348-352, MIT Press 1986

[Verbatim excerpt.] "The T-C problem. ... The problem is to discriminate between a T and a C independent of
translation and rotation. ... Each of the hidden units, over the receptive field of the hidden units ... In order
that the learning that occurred be independent of where on the field the pattern appeared, we constrained all of
the units to learn exactly the same pattern of weights. In this way each unit was constrained to compute exactly
the same function over its receptive field-the receptive fields were constrained to all have the same shape. This
guarantees translation independence and avoids any possible "edge effects" in the learning. The learning can
readily be extended to arbitrarily large fields of input units. This constraint was accomplished by simply adding
together the weight changes dictated by the delta rule for each unit and then changing all weights exactly the
same amount."

[Footnote in the same section, verbatim:] "Terry Sejnowski pointed out to us that the T-C problem was difficult
for models of this sort to learn and therefore worthy of study."

[Context, paraphrase:] The hidden units in this experiment each look at a 3x3 region of the input field (a local
receptive field), one hidden unit per position, and the single output unit sums all hidden units. The figures
show that the shared receptive field learned in different runs became an on-center-off-surround T detector, a
vertical bar detector, a diagonal detector, or a "compactness" inhibitory detector, each of which solves the
discrimination at any position.
