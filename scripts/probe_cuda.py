"""Manual CUDA driver/kernel check; no PyTorch, model training or performance claim."""


def main():
    import ctypes as c,json
    cuda=c.CDLL("libcuda.so.1")
    def call(name,types,*args):
     f=getattr(cuda,name);f.argtypes=types;f.restype=c.c_int
     code=f(*args)
     if code:raise RuntimeError(name+" failed: "+str(code))
    call("cuInit",[c.c_uint],0)
    device=c.c_int();call("cuDeviceGet",[c.POINTER(c.c_int),c.c_int],c.byref(device),0)
    ctx=c.c_void_p();call("cuCtxCreate_v2",[c.POINTER(c.c_void_p),c.c_uint,c.c_int],c.byref(ctx),0,device)
    module=c.c_void_p();mem=c.c_uint64()
    try:
     ptx=c.create_string_buffer(b""".version 7.0
    .target sm_52
    .address_size 64
    .visible .entry add_values(.param .u64 dst,.param .u32 x,.param .u32 y) {
     .reg .b64 %rd;
     .reg .b32 %a, %b, %sum;
     ld.param.u64 %rd, [dst];
     ld.param.u32 %a, [x];
     ld.param.u32 %b, [y];
     add.u32 %sum, %a, %b;
     st.global.u32 [%rd], %sum;
     ret;
    }
    """)
     call("cuModuleLoadData",[c.POINTER(c.c_void_p),c.c_void_p],c.byref(module),c.cast(ptx,c.c_void_p))
     fn=c.c_void_p();call("cuModuleGetFunction",[c.POINTER(c.c_void_p),c.c_void_p,c.c_char_p],c.byref(fn),module,b"add_values")
     call("cuMemAlloc_v2",[c.POINTER(c.c_uint64),c.c_size_t],c.byref(mem),4)
     x=c.c_uint(19);y=c.c_uint(23)
     params=(c.c_void_p*3)(c.cast(c.byref(mem),c.c_void_p),c.cast(c.byref(x),c.c_void_p),c.cast(c.byref(y),c.c_void_p))
     call("cuLaunchKernel",[c.c_void_p]+[c.c_uint]*7+[c.c_void_p,c.POINTER(c.c_void_p),c.c_void_p],fn,1,1,1,1,1,1,0,None,params,None)
     call("cuCtxSynchronize",[])
     result=c.c_uint();call("cuMemcpyDtoH_v2",[c.c_void_p,c.c_uint64,c.c_size_t],c.byref(result),mem,4)
     assert result.value==42
     print(json.dumps({"cuda_kernel_completed":True,"inputs":[19,23],"output":result.value,"scope":"Driver API kernel, not neural training or a throughput benchmark"}))
    finally:
     if mem.value:call("cuMemFree_v2",[c.c_uint64],mem)
     if module.value:call("cuModuleUnload",[c.c_void_p],module)
     call("cuCtxDestroy_v2",[c.c_void_p],ctx)


if __name__ == '__main__':
    main()
