# Neocognitron: A self-organizing neural network model for a mechanism of pattern recognition unaffected by shift in position

Date: 1980
Kind: paraphrase
Source: K. Fukushima, Biological Cybernetics 36:193-202, 1980

[Paraphrase, not verbatim.] The neocognitron is a multilayered network for visual pattern recognition whose
response is not affected by a shift in position of the input pattern, and is tolerant to some deformation. It is
built from alternating layers of two cell types modelled on Hubel and Wiesel's simple and complex cells. Each
S-layer consists of several "cell planes"; all cells in one plane have input connections of the same spatial
distribution, differing only in the position of the small receptive field they look at, so a plane extracts the
same local feature everywhere in the input. The C-layer that follows has fixed, non-modifiable connections: each
C-cell takes excitatory input from a group of S-cells of the same plane at slightly different positions, so it
responds when the feature is present anywhere in that neighbourhood, which makes the representation less
sensitive to position. Modules of S-layer plus C-layer are stacked; receptive fields grow and the number of cells
per plane shrinks with depth, until the last layer has one cell per category. Learning is unsupervised
self-organization without a teacher: only the S-cell input connections are modifiable, and they are reinforced in
a winner-take-all manner so that, after repeated presentation of stimulus patterns, each pattern drives one cell of
the last layer. No error signal is propagated from the output back to earlier layers.
