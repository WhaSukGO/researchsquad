# Neocognitron: A new algorithm for pattern recognition tolerant of deformations and shifts in position

Date: 1982
Kind: paraphrase
Source: K. Fukushima and S. Miyake, Pattern Recognition 15(6):455-469, 1982

[Paraphrase, not verbatim.] This paper restates the neocognitron for a pattern recognition audience and applies it
to handwritten numerals 0-9. The architecture is the alternating S/C cascade: S-cells detect local features with
modifiable input connections shared across a cell plane, C-cells blur the position of each detected feature by
pooling over a neighbourhood with fixed connections, and the alternation is repeated so that the network becomes
progressively more tolerant to shift and distortion while the features become more global. Training is
self-organizing with a "seed cell" procedure, or alternatively supervised in the sense that the experimenter
chooses training patterns for each feature-extracting plane; in neither case is an output error back-propagated
through the layers. The authors report correct recognition of many distorted and shifted numerals and argue that
the alternating local-feature / position-tolerance structure is the mechanism that gives the invariance.
