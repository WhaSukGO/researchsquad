# SN: A simulator for connectionist models

Date: 1988
Kind: paraphrase
Source: L. Bottou and Y. Le Cun, Proceedings of NeuroNimes 88, Nimes, France, pp. 371-382

[Paraphrase, not verbatim.] SN is a simulator for neural networks built around a small Lisp-like interpreter
written in C. Networks are described by connecting units and layers in the interpreter; the numerical kernels
(forward propagation, back-propagation of gradients, weight updates) are compiled C routines called from the
interpreted language, so experiments can be scripted interactively without recompilation while running at compiled
speed. The simulator supports arbitrary feed-forward architectures, weight sharing among connections, and
second-order variants of back-propagation. Work on SN began in 1987; its authors describe it as the tool with
which their handwriting recognition experiments were carried out.
