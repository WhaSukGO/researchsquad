# VLSI implementation of a neural network memory with several hundreds of neurons

Date: 1987
Kind: paraphrase
Source: H. P. Graf, L. D. Jackel, R. E. Howard, B. Straughn, J. S. Denker, W. Hubbard, D. M. Tennant and D. Schwartz, AIP Conf. Proc. 151, Snowbird 1986/1987; and H. P. Graf and P. de Vegvar, ISSCC 1987

[Paraphrase, not verbatim.] The Holmdel group built analog CMOS chips containing a few hundred amplifier "neurons"
and a programmable resistive connection matrix, able to compute a full matrix-vector product between a binary
input vector and stored weights in a single parallel step. Weights are stored as digital bits that switch
resistors on or off, so weight precision is low and the number of weights on a chip is limited to a few thousand
connections; evaluation is fast (microseconds) and the chip can be reused serially for larger computations by
reloading weights. Such a chip can apply the same small template at every location of an image by feeding it
successive image windows, which the group used for template matching in image preprocessing. Hardware
considerations therefore favour networks with few distinct weights and with repeated use of the same weights.
