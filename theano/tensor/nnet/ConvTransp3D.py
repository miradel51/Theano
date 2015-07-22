from __future__ import print_function

import numpy as N
from six.moves import xrange

import theano
from theano.tensor import basic as T
from theano.misc import strutil
from theano.gradient import grad_undefined
from theano.gradient import DisconnectedType


class ConvTransp3D(theano.Op):
    """ "Transpose" of Conv3D (Conv3D implements multiplication by an implicitly defined matrix W. This implements multiplication by its transpose) """
    def __eq__(self, other):
        return type(self) == type(other)

    def __hash__(self):
        return hash(type(self))

    def c_code_cache_version(self):
        return (3,)

    def make_node(self, W, b, d, H, RShape=None):
        """
        :param W: Weights, filter
        :param b: bias, shape == (W.shape[0],)
        :param d: strides when moving the filter over the input
        :param H: The output of Conv3D
        """
        W_ = T.as_tensor_variable(W)
        b_ = T.as_tensor_variable(b)
        d_ = T.as_tensor_variable(d)
        H_ = T.as_tensor_variable(H)
        if RShape:
            RShape_ = T.as_tensor_variable(RShape)
        else:
            RShape_ = T.as_tensor_variable([-1, -1, -1])

        return theano.Apply(self,
                            inputs=[W_, b_, d_, H_, RShape_],
                            outputs=[T.TensorType(H_.dtype,
                                     (False, False, False, False, False))()])

    def infer_shape(self, node, input_shapes):
        W, b, d, H, RShape = node.inputs
        W_shape, b_shape, d_shape, H_shape, RShape_shape = input_shapes
        return [(H_shape[0], RShape[0], RShape[1], RShape[2], W_shape[4])]

    def connection_pattern(self, node):
        return [[True], [True], [True], [True], [False]]

    def grad(self, inputs, output_gradients):
        W, b, d, H, RShape = inputs
        dCdR, = output_gradients
        dCdH = theano.tensor.nnet.conv3D(dCdR, W, T.zeros_like(H[0, 0, 0, 0, :]), d)
        WShape = W.shape
        dCdW = theano.tensor.nnet.convGrad3D(dCdR, d, WShape, H)
        dCdb = T.sum(dCdR, axis=(0, 1, 2, 3))
        # not differentiable, since d affects the output elements
        dCdd = grad_undefined(self, 2, d)
        # disconnected, since RShape just determines the output shape
        dCdRShape = DisconnectedType()()

        if 'name' in dir(dCdR) and dCdR.name is not None:
            dCdR_name = dCdR.name
        else:
            dCdR_name = 'anon_dCdR'

        if 'name' in dir(H) and H.name is not None:
            H_name = H.name
        else:
            H_name = 'anon_H'

        if 'name' in dir(W) and W.name is not None:
            W_name = W.name
        else:
            W_name = 'anon_W'

        if 'name' in dir(b) and b.name is not None:
            b_name = b.name
        else:
            b_name = 'anon_b'

        dCdW.name = ('ConvTransp3D_dCdW.H=' + H_name + ',dCdR=' + dCdR_name +
                     ',W=' + W_name)
        dCdb.name = ('ConvTransp3D_dCdb.H=' + H_name + ',dCdR=' + dCdR_name +
                     ',W=' + W_name + ',b=' + b_name)
        dCdH.name = 'ConvTransp3D_dCdH.H=' + H_name + ',dCdR=' + dCdR_name

        return [dCdW, dCdb, dCdd, dCdH, dCdRShape]

    def perform(self, node, inputs, output_storage):
        W, b, d, H, RShape = inputs
#        print "\t\t\t\tConvTransp3D python code"
        output_storage[0][0] = computeR(W, b, d, H, RShape)

    def c_code(self, node, nodename, inputs, outputs, sub):
        W, b, d, H, RShape = inputs
        fail = sub['fail']

        R = outputs[0]

        codeSource = """
                    ///////////// < code generated by ConvTransp3D >

                    //printf("\t\t\t\tConvTransp3D c code\\n");

                    //Check dimensionality of inputs
                    if (PyArray_NDIM(%(H)s) != 5)
                    {
                        PyErr_Format(PyExc_ValueError,
                                     "H must be a 5-D tensor but it is %%i-D",
                                     PyArray_NDIM(%(H)s));
                        %(fail)s
                    }

                    if (PyArray_NDIM(%(W)s) != 5)
                    {
                         PyErr_Format(PyExc_ValueError, "ConvTransp3D: W must be a 5-D tensor");
                %(fail)s
                    }

                    if (PyArray_NDIM(%(b)s) != 1)
                    {
                         PyErr_Format(PyExc_ValueError, "ConvTransp3D: b must be a vector");
                         %(fail)s
                    }

                    if (PyArray_NDIM(%(d)s) != 1)
                    {
                         PyErr_Format(PyExc_ValueError, "ConvTransp3D: d must be a vector");
                         %(fail)s
                    }

                    //Read and check stride arguments
                    if (PyArray_DIMS(%(d)s)[0] != 3)
                    {
                         PyErr_Format(PyExc_ValueError, "ConvTransp3D: 3 stride length arguments expected (for row, col, and time) but %%li were given", (long)PyArray_DIMS(%(d)s)[0] );
                         %(fail)s
                    }

                    { // for fail 1
                         int dr = *(dtype_%(d)s*)PyArray_GETPTR1(%(d)s,0);
                         int dc = *(dtype_%(d)s*)PyArray_GETPTR1(%(d)s,1);
                         int dt = *(dtype_%(d)s*)PyArray_GETPTR1(%(d)s,2);

                         if (dr <= 0 || dc <= 0 || dt <= 0)
                         {
                             PyErr_Format(PyExc_ValueError, "ConvTransp3D: Strides must all be positive but are %%i, %%i, %%i",dr,dc,dt);
                             %(fail)s
                          }


                         //Read and check sizes of inputs

                        { // for fail 2
                            const int batchSize = PyArray_DIMS(%(H)s)[0];
                            const int outputChannels =  PyArray_DIMS(%(W)s)[0];

                            if (PyArray_DIMS(%(H)s)[4] != outputChannels)
                            {
                                PyErr_Format(PyExc_ValueError, "W produces a %%i channel image but the image has %%li channels. W.shape: (%%li, %%li, %%li, %%li, %%li) H.shape: (%%li, %%li, %%li, %%li, %%li)", outputChannels, (long)PyArray_DIMS(%(H)s)[4], (long)PyArray_DIMS(%(W)s)[0], (long)PyArray_DIMS(%(W)s)[1], (long)PyArray_DIMS(%(W)s)[2], (long)PyArray_DIMS(%(W)s)[3], (long)PyArray_DIMS(%(W)s)[4], (long)PyArray_DIMS(%(H)s)[0], (long)PyArray_DIMS(%(H)s)[1], (long)PyArray_DIMS(%(H)s)[2], (long)PyArray_DIMS(%(H)s)[3], (long)PyArray_DIMS(%(H)s)[4]);
                                %(fail)s
                            }

                            { // for fail 3

                                const int inputChannels = PyArray_DIMS(%(W)s)[4];

                                if (PyArray_DIMS(%(b)s)[0] != inputChannels)
                                {
                                    PyErr_Format(PyExc_ValueError, "ConvTransp3D: b operates on a %%li channel image but the image has %%i channels", (long)PyArray_DIMS(%(b)s)[0], inputChannels );
                                    %(fail)s
                                }

                                { // for fail 4

                                const int filterHeight = PyArray_DIMS(%(W)s)[1];
                                const int filterWidth = PyArray_DIMS(%(W)s)[2];
                                const int filterDur = PyArray_DIMS(%(W)s)[3];
                                const int outputHeight = PyArray_DIMS(%(H)s)[1];
                                const int outputWidth = PyArray_DIMS(%(H)s)[2];
                                const int outputDur = PyArray_DIMS(%(H)s)[3];

                                int videoHeight = (outputHeight-1) * dr + filterHeight;
                                int videoWidth = (outputWidth-1) * dc + filterWidth;
                                int videoDur = (outputDur-1) * dt + filterDur;

                                if (%(RShape)s)
                                {
                                    if (PyArray_NDIM(%(RShape)s) != 1)
                                    {
                                        PyErr_Format(PyExc_ValueError, "ConvTransp3D: RShape must be a vector");
                                        %(fail)s
                                    }

                                    if (PyArray_DIMS(%(RShape)s)[0] != 3)
                                    {
                                        PyErr_Format(PyExc_ValueError, "RShape must specify a 3D shape ( [height,width,duration] )");
                                        %(fail)s
                                    }

                                    dtype_%(RShape)s RShape0 = *(dtype_%(RShape)s*)PyArray_GETPTR1(%(RShape)s,0);
                                    dtype_%(RShape)s RShape1 = *(dtype_%(RShape)s*)PyArray_GETPTR1(%(RShape)s,1);
                                    dtype_%(RShape)s RShape2 = *(dtype_%(RShape)s*)PyArray_GETPTR1(%(RShape)s,2);

                                    if (RShape0 != -1)
                                    {
                                        if (RShape0 < videoHeight || RShape1 < videoWidth || RShape2 < videoDur)
                                        {
                                            PyErr_Format(PyExc_ValueError, "Reconstruction must have physical shape of at least [%%i,%%i,%%i] but RShape argument requests that it be [%%i,%%i,%%i]\\n",videoHeight,videoWidth,videoDur,(int) RShape0,(int) RShape1,(int) RShape2);
                                            %(fail)s
                                        }

                                        videoHeight = RShape0;
                                        videoWidth = RShape1;
                                        videoDur = RShape2;
                                   }
                               } //closes if RShape

                               { // for fail 5

                                   //Allocate the reconstruction
                                   npy_intp dims[5];
                                   dims[0] = batchSize;
                                   dims[4] = inputChannels;
                                   dims[1] = videoHeight;
                                   dims[2] = videoWidth;
                                   dims[3] = videoDur;

                                   if(!(%(R)s) || PyArray_DIMS(%(R)s)[0]!=dims[0] ||
                                    PyArray_DIMS(%(R)s)[1]!=dims[1] ||
                                    PyArray_DIMS(%(R)s)[2]!=dims[2] ||
                                    PyArray_DIMS(%(R)s)[3]!=dims[3] ||
                                    PyArray_DIMS(%(R)s)[4]!=dims[4])
                                   {
                                       Py_XDECREF(%(R)s);
                                       %(R)s = (PyArrayObject *) PyArray_SimpleNew(5, dims, PyArray_DESCR(%(H)s)->type_num);
                                       if (!(%(R)s)) {
                                           PyErr_Format(PyExc_MemoryError, "ConvTransp3D: could not allocate R");
                                           %(fail)s
                                       }
                                   }

                                   { // for fail 6

                                       #define ELEM5(x, i,j,k,l,m) * ( dtype_ ## x *) ( PyArray_BYTES(x) + (i)*PyArray_STRIDES(x)[0]+(j)*PyArray_STRIDES(x)[1]+(k)*PyArray_STRIDES(x)[2]+(l)*PyArray_STRIDES(x)[3]+(m)*PyArray_STRIDES(x)[4] )
                                       #define ELEM_AT(x, i) * ( dtype_ ## x *) ( PyArray_BYTES(x) + (i) )



                                       dtype_%(b)s * b = (dtype_%(b)s *) PyArray_DATA(%(b)s);

                                       int rs4 = PyArray_STRIDES(%(R)s)[4];
                                       int ws0 = PyArray_STRIDES(%(W)s)[0];
                                       int ws4 = PyArray_STRIDES(%(W)s)[4];
                                       int hs4 = PyArray_STRIDES(%(H)s)[4];

                                       // Compute R
                                       // R[i,r,c,t,j] = b_j + sum_{rc,rk | d \circ rc + rk = r} sum_{cc,ck | ...} sum_{tc,tk | ...} sum_k W[k, rk, ck, tk,j] * H[i,rc,cc,tc,k]

                                       for (int i = 0; i < batchSize; i++) {
                                        for (int r = 0; r < videoHeight; r++) {
                                         const int frc = (int)std::max(0.0f, ceilf(float(r-filterHeight+1)/float(dr)));
                                         for (int c = 0; c < videoWidth; c++) {
                                          const int fcc = (int)std::max(0.0f, ceilf(float(c-filterWidth +1)/float(dc)));
                                          for (int t = 0; t < videoDur; t++) {
                                           const int ftc = (int)std::max(0.0f, ceilf(float(t-filterDur +1)  /float(dt)));

                                           long long Rpost = i * PyArray_STRIDES(%(R)s)[0] + r * PyArray_STRIDES(%(R)s)[1] + c * PyArray_STRIDES(%(R)s)[2] + t * PyArray_STRIDES(%(R)s)[3];

                                           long long Rpos = Rpost;
                                           for (int j = 0; j < inputChannels; j++)
                                           {
                                            //ELEM5(%(R)s, i,r,c,t,j) = b[j];
                                            ELEM_AT(%(R)s,Rpos) = b[j];
                                            Rpos += rs4;
                                           }


                                           for (int rc = frc; rc < outputHeight; rc++) {
                                            const int rk = r - rc * dr;
                                            if (rk < 0) break;

                                            for (int cc = fcc; cc < outputWidth; cc++) {
                                             const int ck = c - cc * dc;
                                             if (ck < 0) break;

                                             for (int tc = ftc; tc < outputDur; tc++)
                                             {
                                              const int tk = t - tc * dt;
                                              if (tk < 0) break;

                                              int Wpos = rk * PyArray_STRIDES(%(W)s)[1] +  ck * PyArray_STRIDES(%(W)s)[2] + tk * PyArray_STRIDES(%(W)s)[3];
                                              int Hpostc = i * PyArray_STRIDES(%(H)s)[0] +      rc * PyArray_STRIDES(%(H)s)[1] +  cc * PyArray_STRIDES(%(H)s)[2] + tc * PyArray_STRIDES(%(H)s)[3];
                                              Rpos = Rpost;
                                              for (int j = 0; j < inputChannels; j++)
                                              {
                                               int Wposj = Wpos;
                                               dtype_%(R)s & writePos = ELEM_AT(%(R)s,Rpos);

                                               int Hpos = Hpostc;

                                               for (int k = 0; k < outputChannels; k++) {
                                                //TODO-- it's probably bad in terms of cache that our inner loop is over the largest stride of W.... maybe OK since it's the smallest stride of H
                                                //writePos += ELEM5(%(W)s,k,rk,ck,tk,j) * ELEM5(%(H)s,i,rc,cc,tc,k);
                                                //writePos += ELEM_AT(%(W)s,Wpos) * ELEM_AT(%(H)s,Hpos);

                                                writePos  += ELEM_AT(%(W)s,Wpos) * ELEM_AT(%(H)s,Hpos);

                                                Wpos += ws0;
                                                Hpos += hs4;

                                               } //close the k loop
                                               Rpos += rs4;
                                               Wpos = Wposj +  ws4;
                                              } //close the j loop
                                             } // close the tc loop
                                            } //cc
                                           } //rc
                                          } //t
                                         } //c
                                        } //r
                                       } //i
                                   } //for fail 6
                               } //for fail 5
                           } //for fail 4
                       } //for fail 3
                   } //for fail 2
               } // for fail 1
               ///////////// < /code generated by ConvTransp3D >
                     """

        return strutil.render_string(codeSource, locals())


convTransp3D = ConvTransp3D()

# If the input size wasn't a multiple of D we may need to cause some automatic padding to get the right size of reconstruction


def computeR(W, b, d, H, Rshape=None):
    assert len(W.shape) == 5
    assert len(H.shape) == 5
    assert len(b.shape) == 1
    assert len(d) == 3

    outputChannels, filterHeight, filterWidth, filterDur, \
        inputChannels = W.shape
    batchSize, outputHeight, outputWidth, outputDur, \
        outputChannelsAgain = H.shape
    assert outputChannelsAgain == outputChannels
    assert b.shape[0] == inputChannels

    dr, dc, dt = d
    assert dr > 0
    assert dc > 0
    assert dt > 0

    videoHeight = (outputHeight - 1) * dr + filterHeight
    videoWidth = (outputWidth - 1) * dc + filterWidth
    videoDur = (outputDur - 1) * dt + filterDur

    if Rshape is not None and Rshape[0] != -1:
        if Rshape[0] < videoHeight:
            print((Rshape[0], videoHeight))
            assert False
        assert Rshape[1] >= videoWidth
        assert Rshape[2] >= videoDur

        # print "setting video size to Rshape = "+str(Rshape)

        videoHeight, videoWidth, videoDur = Rshape
    # else:
    #       print "No Rshape passed in"

    # print "video size: "+str((videoHeight, videoWidth, videoDur))

    R = N.zeros((batchSize, videoHeight,
                videoWidth, videoDur, inputChannels), dtype=H.dtype)

    # R[i,j,r,c,t] = b_j + sum_{rc,rk | d \circ rc + rk = r} sum_{cc,ck | ...} sum_{tc,tk | ...} sum_k W[k, j, rk, ck, tk] * H[i,k,rc,cc,tc]
    for i in xrange(0, batchSize):
        # print '\texample '+str(i+1)+'/'+str(batchSize)
        for j in xrange(0, inputChannels):
            # print '\t\tfeature map '+str(j+1)+'/'+str(inputChannels)
            for r in xrange(0, videoHeight):
                # print '\t\t\trow '+str(r+1)+'/'+str(videoHeight)
                for c in xrange(0, videoWidth):
                    for t in xrange(0, videoDur):
                        R[i, r, c, t, j] = b[j]

                        ftc = max([0, int(N.ceil(
                            float(t - filterDur + 1) / float(dt)))])
                        fcc = max([0, int(N.ceil(
                            float(c - filterWidth + 1) / float(dc)))])

                        rc = max([0, int(N.ceil(
                            float(r - filterHeight + 1) / float(dr)))])
                        while rc < outputHeight:
                            rk = r - rc * dr
                            if rk < 0:
                                break

                            cc = fcc
                            while cc < outputWidth:
                                ck = c - cc * dc
                                if ck < 0:
                                    break

                                tc = ftc
                                while tc < outputDur:
                                    tk = t - tc * dt
                                    if tk < 0:
                                        break

                                    R[i, r, c, t, j] += N.dot(
                                        W[:, rk, ck, tk, j], H[i, rc, cc, tc, :])

                                    tc += 1
                                ""  # close loop over tc
                                cc += 1
                            ""  # close loop over cc

                            rc += 1
                        ""  # close loop over rc
                    ""  # close loop over t
                ""  # close loop over c
            ""  # close loop over r
        ""  # close loop over j
    ""  # close loop over i

    return R
