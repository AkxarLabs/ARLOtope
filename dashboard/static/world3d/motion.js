/* Bounded semantic clips. No executable authoring or arbitrary Three property paths. */
(function () {
  'use strict'; const L = window.Lab3D;
  const channels = { lean: [-Math.PI,Math.PI], tilt: [-Math.PI,Math.PI], turn: [-8*Math.PI,8*Math.PI], roll: [-2*Math.PI,2*Math.PI], bob: [-.3,.5],
    armL: [-2*Math.PI,2*Math.PI], armR: [-2*Math.PI,2*Math.PI], raiseL: [-Math.PI,2*Math.PI], raiseR: [-Math.PI,2*Math.PI],
    leg0: [-Math.PI,Math.PI], leg1: [-Math.PI,Math.PI], look: [-1,1], sq: [-.6,.6] };
  const clips = {
    wave:{duration:1.2,tracks:{raiseR:[[0,0],[.2,2.5],[1,2.5],[1.2,0]],armR:[[0,-.35],[.3,-.7],[.45,-.2],[.6,-.7],[.8,-.2],[1.2,-.35]],tilt:[[0,0],[.3,-.1],[1.2,0]]}},
    nod:{duration:.8,tracks:{tilt:[[0,0],[.25,.25],[.5,-.06],[.8,0]]}},
    curious:{duration:1.8,tracks:{tilt:[[0,0],[.4,-.15],[1.2,-.15],[1.8,0]],roll:[[0,0],[.4,.12],[1.2,.12],[1.8,0]],look:[[0,0],[.6,.6],[1.8,0]]}},
    stretch:{duration:2,tracks:{raiseL:[[0,0],[.5,2],[1.4,2],[2,0]],raiseR:[[0,0],[.5,2],[1.4,2],[2,0]],lean:[[0,0],[.6,-.14],[2,0]]}},
    puzzled:{duration:1.5,tracks:{tilt:[[0,0],[.4,.15],[1.5,0]],raiseR:[[0,0],[.3,.5],[1.1,.5],[1.5,0]],armR:[[0,-.35],[.3,-2],[1.1,-2],[1.5,-.35]]}},
    contact:{duration:.55,tracks:{lean:[[0,0],[.1,-.15],[.55,0]],roll:[[0,0],[.15,.1],[.55,0]]}},
    settle:{duration:1.5,tracks:{bob:[[0,0],[.4,-.03],[1.5,0]],tilt:[[0,0],[.5,.2],[1.5,0]]}},
    happy:{duration:1,tracks:{bob:[[0,0],[.2,.08],[.45,0],[.7,.05],[1,0]],sq:[[0,0],[.1,-.06],[.2,.07],[.45,0],[1,0]]}},
  };
  function validate(clip,depth=0) {
    if (!clip || depth>=8 || !Number.isFinite(clip.duration) || clip.duration < .01 || clip.duration > 300 || Object.keys(clip.tracks||{}).length > Object.keys(channels).length || !['smooth','linear','step'].includes(clip.easing||'smooth')) throw new Error('Invalid clip duration/tracks');
    for (const [name, keys] of Object.entries(clip.tracks||{})) {
      const range = channels[name]; if (!range || !Array.isArray(keys) || keys.length < 2 || keys.length > 1024) throw new Error('Invalid clip channel: '+name);
      let last = -1; for (const key of keys) {
        if (!Array.isArray(key) || key.length!==2 || !key.every(Number.isFinite) || key[0]<0 || key[0]>clip.duration || key[0]<=last || key[1]<range[0] || key[1]>range[1]) throw new Error('Invalid keyframe: '+name); last=key[0];
      }
    }
    if(!Array.isArray(clip.segments||[])||(clip.segments||[]).length>128)throw new Error('Invalid clip segments');
    for(const s of clip.segments||[]){if(!Number.isFinite(s.at)||s.at<0||s.at>clip.duration||!Number.isFinite(s.rate??1)||(s.rate??1)<=0||(s.rate??1)>100||!Number.isFinite(s.weight??1)||Math.abs(s.weight??1)>4)throw new Error('Invalid segment timing/weight');validate(s.clip,depth+1)}
    return clip;
  }
  function sample(clip,time) {
    const t=clip.loop?((time%clip.duration)+clip.duration)%clip.duration:Math.max(0,Math.min(time,clip.duration)),out={};
    for(const [name,keys] of Object.entries(clip.tracks||{})) {
      let i=1;while(i<keys.length-1&&keys[i][0]<t)i++;
      const a=keys[i-1],b=keys[i],u=Math.max(0,Math.min(1,(t-a[0])/(b[0]-a[0]))),k=clip.easing==='linear'?u:clip.easing==='step'?(u===1?1:0):u*u*(3-2*u);out[name]=a[1]+(b[1]-a[1])*k;
    }
    for(const s of clip.segments||[]){const elapsed=(t-s.at)*(s.rate??1);if(elapsed<0||(!s.clip.loop&&elapsed>s.clip.duration))continue;for(const [name,v]of Object.entries(sample(s.clip,elapsed)))out[name]=(out[name]||0)+v*(s.weight??1)}
    for(const name of Object.keys(out))out[name]=Math.max(channels[name][0],Math.min(channels[name][1],out[name]));
    return out;
  }
  Object.values(clips).forEach(validate);
  L.motion={channels,clips,validate,sample,register(id,clip){if(!/^local\/[a-z0-9.-]+$/.test(id))throw new Error('Custom clip needs local/ id');clips[id]=validate(clip);},
    player(seed=0){let active=null,last=-100,next=5+(Number(seed)%7);return {
      play(id,t){if(!clips[id])return false;active={id,start:t};last=t;return true;},
      update(t,state){
        if(state.motion&&state.motion!=='full'){active=null;return {};}
        if(state.gesture===false)active=null;
        if(state.contact&&!active&&t-last>3)this.play('contact',t);
        if(state.gesture)this.play(state.gesture,t);
        if(!active&&state.pose==='idle'&&!state.moving&&t>next){this.play(['curious','nod','stretch'][Math.abs(Math.floor(seed+t/8))%3],t);next=t+10+(Number(seed)%9);}
        if(!active)return {};
        const clip=clips[active.id];if(!clip){active=null;return {};}
        const elapsed=t-active.start;if(elapsed>clip.duration&&!clip.loop){active=null;return {};}
        return sample(clip,elapsed);
      },snapshot(){return {active:active&&{...active},last,next};},restore(s){if(s){active=s.active;last=s.last;next=s.next;}}
    };}
  };
})();
