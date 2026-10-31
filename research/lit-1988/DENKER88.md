# Neural network recognizer for hand-written zip code digits

Date: 1988
Kind: excerpt
Source: J. S. Denker, W. R. Gardner, H. P. Graf, D. Henderson, R. E. Howard, W. Hubbard, L. D. Jackel, H. S. Baird and I. Guyon, Advances in Neural Information Processing Systems 1 (NIPS 1988), pp. 323-331

[Verbatim excerpts.] "This paper describes the construction of a system that recognizes hand-printed digits, using
a combination of classical techniques and neural-net methods. The system has been trained and tested on real-world
data, derived from zipcodes seen on actual U.S. Mail. The system rejects a small percentage of the examples as
unclassifiable, and achieves a very low error rate on the remaining examples."

"Broadly speaking, the recognizer is divided into the preprocessor and the classifier. The two main ideas behind
the preprocessor are (1) to remove meaningless variations (i.e. noise) and (2) to capture meaningful variations
(i.e. salient features)."

"Most of the results reported in this paper are based on a collection of digits taken from hand-written Zip Codes
that appeared on real U.S. Mail passing through the Buffalo, N.Y. post office. ... The digits were written by many
different people, using a great variety of writing styles and instruments, with widely varying levels of care."

"Acquisition, binarization, location, and preliminary segmentation were performed by Postal Service contractors."

Scaling and deskewing: "A translation and scale factor are then applied to make the image fit in a rectangle 20 x
32 pixels. ... we calculate the XY and YY moments of the image, and apply a linear transformation that drives the
XY moment to zero. The transformation is a pure shear, not a rotation."

Skeletonization: "By deleting pixels at the boundaries of thick strokes. ... This can be formulated as a pattern
matching problem - we search the image looking for situations in which a pixel should be deleted. The decisions
can be expressed as a convolution, using a rather small kernel, since the identical decision process is repeated
for each location in the image ... 5 x 5 templates are convenient, powerful, and flexible." "The inner three loops
... are performed in parallel, in a single cycle of our special-purpose chip."

Feature maps: "It is known from biological studies [Hubel and Wiesel 1962] that the human vision system is
sensitive to certain features that occur in images, particularly lines and the ends of lines. We therefore
designed detectors for such features. ... Once again we use a convolutional method for locating the features of
interest - we check each location in the image to see if each particular feature is present there. ... The
feature extractor templates are 7 x 7 pixels ... There are 49 different feature extractor templates. The output of
each is stored separately. These outputs are called feature maps, since they show what feature(s) occurred where
in the image." "There are 18 combined features, and these are what is passed to the next stage."

Coarse blocking: "If a certain image contains a particular feature (say a left-hand stroke end) in the upper left
corner, it is not really necessary to specify the location of that feature with great precision. ... We call this
Coarse Blocking or Coarse Coding of the feature maps. We find that 3 x 5 is sufficient resolution."

Classifiers: "it is critically important for the system to provide estimates of its confidence, and to reject
digits rather than misclassify them." [The classifier stage, an adaptive network on the 18 x 3 x 5 coarse-coded
features, is the only trained part; all templates above are hand-designed constants.]
