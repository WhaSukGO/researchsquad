# Phoneme recognition using time-delay neural networks

Date: 1987
Kind: paraphrase
Source: A. Waibel, T. Hanazawa, G. Hinton, K. Shikano and K. Lang, ATR Technical Report TR-I-0006, October 1987 (later IEEE Trans. ASSP 37(3):328-339, 1989)

[Paraphrase, not verbatim.] The time-delay neural network (TDNN) is a three-layer network for recognizing phonemes
in spectrogram inputs, trained with error back-propagation. Each hidden unit looks at a short window of a few
consecutive time frames (a receptive field in time), and the same unit, with the same weights, is replicated at
every time position: weights are shared across time, and during training the weight changes computed at all
positions are added together so that the replicated units remain identical. The next layer again looks at a
window over the hidden layer, and the output unit integrates over all positions. Because the detectors are the
same at every time step, the network recognizes acoustic-phonetic features regardless of when they occur in the
window, so temporal shifts of the input do not blur the features. On the /b/, /d/, /g/ task the TDNN reached
98.5% correct against 93.7% for a hidden Markov model trained on the same data.
