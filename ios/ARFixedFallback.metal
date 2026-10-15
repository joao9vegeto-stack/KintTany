#include <metal_stdlib>
using namespace metal;
struct ProbeIn {
 float4 a0 [[attribute(0)]];
 float4 a3 [[attribute(3)]];
};
struct ProbeCB {
 float4 vp_c[512];
 float4 vp_posscale;
 float4 vp_posoffset;
};
struct ProbeOut {
 float4 pos [[position]];
 float4 col0;
};
vertex ProbeOut ar_fixed_vertex(ProbeIn v [[stage_in]], constant ProbeCB &c [[buffer(0)]]) {
 float4 p=float4(dot(c.vp_c[0],v.a0),dot(c.vp_c[1],v.a0),
                 dot(c.vp_c[2],v.a0),dot(c.vp_c[3],v.a0));
 float m=dot(abs(c.vp_c[0]),float4(1.0))+
         dot(abs(c.vp_c[1]),float4(1.0))+
         dot(abs(c.vp_c[2]),float4(1.0))+
         dot(abs(c.vp_c[3]),float4(1.0));
 if(m==0.0) p=v.a0;
 ProbeOut o;
 o.pos=float4(p.xyz*c.vp_posscale.xyz+p.w*c.vp_posoffset.xyz,p.w);
 o.col0=v.a3;
 return o;
}
fragment float4 ar_fixed_fragment(ProbeOut input [[stage_in]]) {
 return input.col0;
}
