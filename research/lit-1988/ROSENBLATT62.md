# Principles of Neurodynamics: Perceptrons and the Theory of Brain Mechanisms

Date: 1962
Kind: paraphrase
Source: F. Rosenblatt, Spartan Books, 1962

[Paraphrase, not verbatim.] Rosenblatt's perceptron is a layered network of threshold units. Sensory units
(the retina) connect to association units through fixed, randomly chosen local connections, each association
unit looking at a small patch of the retina; the association units connect to response units through adjustable
weights. Only the last layer of weights is trained, by the perceptron error-correction rule: when the response is
wrong, move the weights toward the input (or away from it). Rosenblatt proved that if a linear separation of the
association-unit activities exists, the rule finds one in finitely many corrections (the perceptron convergence
theorem). He discussed multilayer perceptrons with several adjustable layers and reported that no satisfactory
learning procedure for the intermediate layers was known; he proposed "back-coupled" error correction heuristics
without a convergence guarantee. Local receptive fields connecting units to small regions of the input appear
here as a design device for visual pattern recognition.
