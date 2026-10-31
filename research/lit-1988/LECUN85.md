# Une procedure d'apprentissage pour reseau a seuil asymetrique (A learning scheme for asymmetric threshold networks)

Date: 1985
Kind: paraphrase
Source: Y. Le Cun, Proceedings of Cognitiva 85, Paris, pp. 599-604, June 1985; English version 'Learning processes in an asymmetric threshold network', in Disordered Systems and Biological Organization, Springer 1986

[Paraphrase of the author's own later description.] The paper proposes a learning procedure for multilayer
networks of threshold-like units with asymmetric (feed-forward) connections. Instead of propagating error
gradients, the procedure propagates "virtual target values" for the hidden units backwards from the output
layer: each hidden unit receives a desired state computed from the desired states of the units it feeds, and
every layer is then trained with a local delta-type rule toward its targets. In a special form the procedure is
equivalent to gradient back-propagation of the output error. The author later wrote that he had proposed the
algorithm during his DEA work in 1983/1984 without a theoretical justification at the time. The paper was read by
G. Hinton, who had come to Paris for the same conference, and led to the author's visit to Toronto.
