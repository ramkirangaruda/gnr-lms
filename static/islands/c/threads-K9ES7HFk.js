import{A as F,y as se,u as O,B as Le}from"./compat.module-DLmNVnBc.js";const Be=`#version 300 es
precision highp float;
in vec2 aPoint;
uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uFrame;
uniform float uAmplitude;
uniform float uDistance;
uniform vec2 uMouse;
uniform float uCount;
uniform float uThickness;
uniform float uSoftness;
uniform float uWaves;
uniform float uSplit;
uniform float uFray;
uniform float uSeed;
uniform vec2 uTurn;
uniform vec4 uPart;
uniform float uTaper;
out float vEdge;
out float vBand;
out float vDraw;
out float vAlpha;
out float vIndex;

float Perlin2D(vec2 P) {
  vec2 Pi = floor(P);
  vec4 Pf_Pfmin1 = P.xyxy - vec4(Pi, Pi + 1.0);
  vec4 Pt = vec4(Pi.xy, Pi.xy + 1.0);
  Pt = Pt - floor(Pt * (1.0 / 71.0)) * 71.0;
  Pt += vec2(26.0, 161.0).xyxy;
  Pt *= Pt;
  Pt = Pt.xzxz * Pt.yyww;
  vec4 hash_x = fract(Pt * (1.0 / 951.135664));
  vec4 hash_y = fract(Pt * (1.0 / 642.949883));
  vec4 grad_x = hash_x - 0.49999;
  vec4 grad_y = hash_y - 0.49999;
  vec4 grad_results = inversesqrt(grad_x * grad_x + grad_y * grad_y) * (grad_x * Pf_Pfmin1.xzxz + grad_y * Pf_Pfmin1.yyww);
  grad_results *= 1.4142135623730950;
  vec2 blend = Pf_Pfmin1.xy * Pf_Pfmin1.xy * Pf_Pfmin1.xy * (Pf_Pfmin1.xy * (Pf_Pfmin1.xy * 6.0 - 15.0) + 10.0);
  vec4 blend2 = vec4(blend, vec2(1.0 - blend));
  return dot(grad_results, blend2.zxzx * blend2.wwyy);
}

void main() {
  float perc = float(gl_InstanceID) / uCount;
  float x = aPoint.x;
  float pixel = 1.0 / max(uResolution.x, uResolution.y);
  float splitPoint = uSplit + perc * uFray;
  float amplitudeNormal = smoothstep(splitPoint, max(0.7, splitPoint + 0.2), x);
  float finalAmplitude = amplitudeNormal * 0.5 * uAmplitude * (1.0 + (uMouse.y - 0.5) * 0.2);
  float timeScaled = uTime / 10.0 + (uMouse.x - 0.5);
  float blur = smoothstep(splitPoint, splitPoint + 0.05, x) * perc;
  float xnoise = mix(
    Perlin2D(vec2(timeScaled * 2.5 + uSeed, (x * uWaves + perc) * 2.5)),
    Perlin2D(vec2(timeScaled * 3.5 + uSeed, (x * uWaves + timeScaled) * 3.5)) / 1.5,
    x * 0.3
  );
  float y = 0.5 + (perc - 0.5) * uDistance + xnoise / 2.0 * finalAmplitude;
  vec2 local = vec2((x - 0.5) * uFrame.x, (y - 0.5) * uFrame.y);
  if (uPart.z > 0.0) {
    vec2 delta = local - uPart.xy;
    float reach = uPart.w;
    float pull = exp(-dot(delta, delta) / (reach * reach));
    local.y += delta.y * pull * uPart.z;
  }
  float width = 7.0 * uThickness * pixel * (1.0 - perc);
  float band = (width / 2.0 + 10.0 * uSoftness * pixel * blur) * uFrame.y;
  float draw = max(band, 1.0);
  local.y += aPoint.y * draw;
  vec2 turned = vec2(local.x * uTurn.x - local.y * uTurn.y, local.x * uTurn.y + local.y * uTurn.x);
  gl_Position = vec4(turned / (uResolution * 0.5), 0.0, 1.0);
  vEdge = aPoint.y * draw;
  vBand = band;
  vDraw = draw;
  vAlpha = 1.0 - smoothstep(0.0, 1.0, pow(perc, 0.3)) * uTaper;
  vIndex = perc;
}`,Ie=`#version 300 es
precision highp float;
in float vEdge;
in float vBand;
in float vDraw;
in float vAlpha;
in float vIndex;
uniform vec3 uColor;
uniform vec3 uAccent;
out vec4 outColor;
void main() {
  float coverage = (1.0 - smoothstep(0.0, vDraw, abs(vEdge))) * (vBand / vDraw) * vAlpha;
  outColor = vec4(mix(uColor, uAccent, vIndex) * coverage, coverage);
}`,Ne=`#version 300 es
in vec2 aPosition;
out vec2 vUv;
void main() {
  vUv = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`,Oe=`#version 300 es
precision highp float;
in vec2 vUv;
uniform sampler2D uLines;
uniform vec2 uResolution;
uniform float uFade;
uniform float uOpacity;
uniform float uCurve;
out vec4 outColor;

float smootherstep(float edge, float x) {
  float t = clamp(x / edge, 0.0, 1.0);
  return t * t * t * (t * (t * 6.0 - 15.0) + 10.0);
}

void main() {
  vec4 lines = texture(uLines, vUv);
  float alpha = lines.a;
  vec3 color = alpha > 0.0001 ? lines.rgb / alpha : vec3(0.0);
  float mask = uOpacity;
  if (uFade > 0.0) {
    vec2 px = vUv * uResolution;
    float edge = uFade * min(uResolution.x, uResolution.y) * 0.5;
    mask *= smootherstep(edge, px.x) * smootherstep(edge, uResolution.x - px.x);
    mask *= smootherstep(edge, px.y) * smootherstep(edge, uResolution.y - px.y);
  }
  outColor = vec4(color * pow(alpha, uCurve), alpha) * mask;
}`,ue=1920,h=(o,i,f)=>Math.min(f,Math.max(i,o)),ce=(o,i,f)=>{const l=o.createShader(i);return l?(o.shaderSource(l,f),o.compileShader(l),o.getShaderParameter(l,o.COMPILE_STATUS)?l:(o.deleteShader(l),null)):null},le=(o,i,f)=>{const l=ce(o,o.VERTEX_SHADER,i),x=ce(o,o.FRAGMENT_SHADER,f),p=o.createProgram();return!l||!x||!p?null:(o.attachShader(p,l),o.attachShader(p,x),o.linkProgram(p),o.deleteShader(l),o.deleteShader(x),o.getProgramParameter(p,o.LINK_STATUS)?p:(o.deleteProgram(p),null))},fe=(o,i,f)=>{const l={};for(const x of f)l[x]=o.getUniformLocation(i,x);return l},Xe=({color:o=[1,1,1],accentColor:i,amplitude:f=1.7,distance:l=.4,enableMouseInteraction:x=!1,lineCount:p=90,thickness:de=.6,softness:me=1.3,speed:he=.6,waves:pe=1.05,split:ve=.04,fray:xe=.5,angle:Pe=25,seed:Ee=0,parting:ge=0,taper:ye=.85,brightness:Re=1.4,fade:Ae=0,opacity:Te=1,paused:be=!1,..._e})=>{const X=F(null),V=F(null),y=F(null),Me=`${Array.isArray(o)?o.join(","):String(o)}|${Array.isArray(i)?i.join(","):String(i!=null?i:"")}`,k={color:o,accentColor:i,colorKey:Me,amplitude:f,distance:l,enableMouseInteraction:x,lineCount:h(Math.round(p),1,400),thickness:Math.max(0,de),softness:Math.max(0,me),speed:he,waves:Math.max(0,pe),split:h(ve,0,1),fray:h(xe,0,1),angle:Pe,seed:Ee,parting:h(ge,0,1),taper:h(ye,0,1),brightness:h(Re,.25,2),fade:h(Ae,0,1),opacity:h(Te,0,1),paused:be},w=F(k);w.current=k,se(()=>{var ee,te;const v=X.current,m=V.current,e=m==null?void 0:m.getContext("webgl2",{alpha:!0,premultipliedAlpha:!0,antialias:!1,depth:!1,stencil:!1});if(!v||!m||!e)return;const R=le(e,Be,Ie),A=le(e,Ne,Oe);if(!R||!A)return;const s=fe(e,R,["uTime","uResolution","uFrame","uAmplitude","uDistance","uMouse","uCount","uThickness","uSoftness","uWaves","uSplit","uFray","uSeed","uTurn","uPart","uTaper","uColor","uAccent"]),T=fe(e,A,["uLines","uResolution","uFade","uOpacity","uCurve"]),S=e.createVertexArray(),D=e.createBuffer();e.bindVertexArray(S),e.bindBuffer(e.ARRAY_BUFFER,D);const G=e.getAttribLocation(R,"aPoint");e.enableVertexAttribArray(G),e.vertexAttribPointer(G,2,e.FLOAT,!1,0,0);const U=e.createVertexArray(),W=e.createBuffer();e.bindVertexArray(U),e.bindBuffer(e.ARRAY_BUFFER,W),e.bufferData(e.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),e.STATIC_DRAW);const Y=e.getAttribLocation(A,"aPosition");e.enableVertexAttribArray(Y),e.vertexAttribPointer(Y,2,e.FLOAT,!1,0,0),e.bindVertexArray(null);const b=e.createTexture(),C=e.createFramebuffer();e.bindTexture(e.TEXTURE_2D,b),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MIN_FILTER,e.NEAREST),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MAG_FILTER,e.NEAREST),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_S,e.CLAMP_TO_EDGE),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_T,e.CLAMP_TO_EDGE);const L=document.createElement("canvas");L.width=1,L.height=1;const P=L.getContext("2d",{willReadFrequently:!0}),we=(te=(ee=window.matchMedia)==null?void 0:ee.call(window,"(prefers-reduced-motion: reduce)").matches)!=null?te:!1,t={time:0,width:1,height:1,segments:0,colorKey:"",color:[1,1,1],accent:[1,1,1],mouse:[.5,.5],targetMouse:[.5,.5],pointer:[0,0],targetPointer:[0,0],presence:0,inside:!1};let E=0,g=0,M=!0,B=!0;const K=r=>{if(Array.isArray(r))return[0,1,2].map(c=>{var d;return h(Number((d=r[c])!=null?d:1),0,1)});if(!P)return[1,1,1];P.clearRect(0,0,1,1),P.fillStyle="#ffffff",P.fillStyle=String(r),P.fillRect(0,0,1,1);const[n,a,u]=P.getImageData(0,0,1,1).data;return[n/255,a/255,u/255]},Se=r=>{r.colorKey!==t.colorKey&&(t.colorKey=r.colorKey,t.color=K(r.color),t.accent=r.accentColor===void 0||r.accentColor===null?t.color:K(r.accentColor))},De=r=>{if(r===t.segments)return;t.segments=r;const n=new Float32Array((r+1)*4);for(let a=0;a<=r;a++){const u=a/r;n.set([u,-1,u,1],a*4)}e.bindBuffer(e.ARRAY_BUFFER,D),e.bufferData(e.ARRAY_BUFFER,n,e.STATIC_DRAW)},q=()=>{const r=Math.max(1,v.clientWidth),n=Math.max(1,v.clientHeight),a=Math.min(window.devicePixelRatio||1,2),u=Math.max(r,n)*a,c=u>ue?a*ue/u:a;m.width=Math.max(1,Math.round(r*c)),m.height=Math.max(1,Math.round(n*c)),t.width=r,t.height=n,e.bindTexture(e.TEXTURE_2D,b),e.texImage2D(e.TEXTURE_2D,0,e.RGBA,m.width,m.height,0,e.RGBA,e.UNSIGNED_BYTE,null),e.bindFramebuffer(e.FRAMEBUFFER,C),e.framebufferTexture2D(e.FRAMEBUFFER,e.COLOR_ATTACHMENT0,e.TEXTURE_2D,b,0),e.bindFramebuffer(e.FRAMEBUFFER,null),De(h(Math.round(r/3),96,640)),I()},I=()=>{const r=w.current;Se(r);const n=m.width,a=m.height,u=r.angle*Math.PI/180,c=Math.cos(u),d=Math.sin(u),N=Math.abs(n*c)+Math.abs(a*d),Ue=Math.abs(n*d)+Math.abs(a*c),re=n/t.width,ne=r.enableMouseInteraction?t.mouse:[.5,.5],Ce=r.parting*t.presence*2,oe=t.pointer[0]*re,ae=t.pointer[1]*re,ie=[oe*c+ae*d,-oe*d+ae*c];e.bindFramebuffer(e.FRAMEBUFFER,C),e.viewport(0,0,n,a),e.clearColor(0,0,0,0),e.clear(e.COLOR_BUFFER_BIT),e.enable(e.BLEND),e.blendFunc(e.ONE,e.ONE_MINUS_SRC_ALPHA),e.useProgram(R),e.uniform1f(s.uTime,t.time),e.uniform2f(s.uResolution,n,a),e.uniform2f(s.uFrame,N,Ue),e.uniform1f(s.uAmplitude,r.amplitude),e.uniform1f(s.uDistance,r.distance),e.uniform2f(s.uMouse,ne[0],ne[1]),e.uniform1f(s.uCount,r.lineCount),e.uniform1f(s.uThickness,r.thickness),e.uniform1f(s.uSoftness,r.softness),e.uniform1f(s.uWaves,r.waves),e.uniform1f(s.uSplit,r.split),e.uniform1f(s.uFray,r.fray),e.uniform1f(s.uSeed,r.seed*13.37),e.uniform2f(s.uTurn,c,d),e.uniform4f(s.uPart,ie[0],ie[1],Ce,Math.min(n,a)*.16),e.uniform1f(s.uTaper,r.taper),e.uniform3f(s.uColor,t.color[0],t.color[1],t.color[2]),e.uniform3f(s.uAccent,t.accent[0],t.accent[1],t.accent[2]),e.bindVertexArray(S),e.drawArraysInstanced(e.TRIANGLE_STRIP,0,(t.segments+1)*2,r.lineCount),e.bindFramebuffer(e.FRAMEBUFFER,null),e.viewport(0,0,n,a),e.disable(e.BLEND),e.clear(e.COLOR_BUFFER_BIT),e.useProgram(A),e.activeTexture(e.TEXTURE0),e.bindTexture(e.TEXTURE_2D,b),e.uniform1i(T.uLines,0),e.uniform2f(T.uResolution,n,a),e.uniform1f(T.uFade,r.fade),e.uniform1f(T.uOpacity,r.opacity),e.uniform1f(T.uCurve,2/r.brightness),e.bindVertexArray(U),e.drawArrays(e.TRIANGLES,0,3),e.bindVertexArray(null)},H=r=>{if(E=0,!B||!M||document.hidden)return;const n=w.current,a=g?Math.min(.05,(r-g)/1e3):1/60;g=r;const u=!n.paused&&!we;u&&(t.time+=a*n.speed);const c=1-Math.exp(-a*3);t.mouse[0]+=(t.targetMouse[0]-t.mouse[0])*c,t.mouse[1]+=(t.targetMouse[1]-t.mouse[1])*c;const d=1-Math.exp(-a*10);t.pointer[0]+=(t.targetPointer[0]-t.pointer[0])*d,t.pointer[1]+=(t.targetPointer[1]-t.pointer[1])*d,t.presence+=((t.inside&&n.parting>0?1:0)-t.presence)*(1-Math.exp(-a*4)),I();const N=Math.abs(t.targetMouse[0]-t.mouse[0])>5e-4||Math.abs(t.targetMouse[1]-t.mouse[1])>5e-4||Math.abs(t.targetPointer[0]-t.pointer[0])>.05||Math.abs(t.targetPointer[1]-t.pointer[1])>.05||Math.abs((t.inside&&n.parting>0?1:0)-t.presence)>.002;u||N?E=requestAnimationFrame(H):g=0},_=()=>{!E&&B&&M&&!document.hidden&&(E=requestAnimationFrame(H))},$=r=>{const n=v.getBoundingClientRect(),a=(r.clientX-n.left)/Math.max(1,n.width),u=(r.clientY-n.top)/Math.max(1,n.height),c=a>=0&&a<=1&&u>=0&&u<=1;c?(t.targetMouse=[a,1-u],t.targetPointer=[r.clientX-n.left-n.width/2,n.height/2-(r.clientY-n.top)],!t.inside&&t.presence<.01&&(t.pointer=[...t.targetPointer])):t.inside&&(t.targetMouse=[.5,.5]),t.inside=c,_()},j=()=>{t.inside=!1,t.targetMouse=[.5,.5],_()},J=()=>{g=0,_()},Q=new ResizeObserver(q);Q.observe(v);const Z=new IntersectionObserver(r=>{M=r.some(n=>n.isIntersecting),M&&(g=0,_())});return Z.observe(v),window.addEventListener("pointermove",$,{passive:!0}),document.documentElement.addEventListener("pointerleave",j),document.addEventListener("visibilitychange",J),q(),y.current=()=>{E||I(),_()},()=>{B=!1,cancelAnimationFrame(E),y.current=null,Q.disconnect(),Z.disconnect(),window.removeEventListener("pointermove",$),document.documentElement.removeEventListener("pointerleave",j),document.removeEventListener("visibilitychange",J),e.deleteFramebuffer(C),e.deleteTexture(b),e.deleteBuffer(D),e.deleteBuffer(W),e.deleteVertexArray(S),e.deleteVertexArray(U),e.deleteProgram(R),e.deleteProgram(A)}},[]),se(()=>{var v;(v=y.current)==null||v.call(y)});const{className:z="",...Fe}=_e;return O("div",{ref:X,className:`threads-container${z?` ${z}`:""}`,...Fe,children:O("canvas",{ref:V,className:"threads-canvas","aria-hidden":"true"})})};function ke(o){const i=window.innerWidth<768,f=navigator.connection;f&&(f.saveData||/2g/.test(f.effectiveType||""))||(Le(O(Xe,{color:"#e10600",accentColor:"#ff5a4f",amplitude:i?1.2:1.6,distance:.3,lineCount:i?40:70,speed:.5,brightness:1.6,enableMouseInteraction:!i}),o),requestAnimationFrame(()=>o.classList.add("is-live")))}export{ke as default};
