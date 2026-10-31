/* Disposable scene annotations: task/evidence links and room clearance previews. */
(function () {
  const L=window.Lab3D;
  L.annotations=(THREE,scene)=>{
    const links=new THREE.Group(),guides=new THREE.Group();scene.add(links,guides);
    const clear=group=>{while(group.children.length)L.resources.release(group.children[group.children.length-1])};
    return {
      links(from,targets,night){
        while(links.children.length>targets.length)L.resources.release(links.children[links.children.length-1]);
        targets.forEach(({at:target,lift,attention},i)=>{
          let line=links.children[i];
          if(!line){
            const geometry=new THREE.BufferGeometry();
            geometry.setAttribute('position',new THREE.BufferAttribute(new Float32Array(51),3));
            geometry.setAttribute('lineDistance',new THREE.BufferAttribute(new Float32Array(17),1));
            line=new THREE.Line(geometry,new THREE.LineDashedMaterial({dashSize:.14,gapSize:.15,transparent:true,opacity:.7,depthTest:false}));
            line.frustumCulled=false;line.renderOrder=5;links.add(line);L.resources.track(line);
          }
          line.material.color.set(attention?(night?'#dcc190':'#886b34'):night?'#9ccfc6':'#365d63');
          const p=line.geometry.attributes.position,d=line.geometry.attributes.lineDistance;
          const height=Math.min(3,Math.hypot(target.x-from.x,target.z-from.z)*.12);let length=0;
          for(let k=0;k<=16;k++){
            const t=k/16,x=from.x+(target.x-from.x)*t,y=from.y+1.25+(target.y+lift-from.y-1.25)*t+Math.sin(Math.PI*t)*height,z=from.z+(target.z-from.z)*t;
            if(k)length+=Math.hypot(x-p.getX(k-1),y-p.getY(k-1),z-p.getZ(k-1));
            p.setXYZ(k,x,y,z);d.setX(k,length);
          }
          p.needsUpdate=d.needsUpdate=true;
        });
      },
      guides(world,roomId,K){
        clear(guides);const room=world.rooms[roomId];if(!room)return;
        const group=new THREE.Group();group.position.set(room.x,0,room.z);group.rotation.y=room.ry;guides.add(group);
        const points=new Set();
        for(const spots of Object.values(room.uses))for(const [x,z] of spots){
          const key=x.toFixed(2)+','+z.toFixed(2);if(points.has(key))continue;points.add(key);
          group.add(K.cyl(.09,.09,.04,'teal',x,.17,z));
        }
        for(const p of (room.spec.props||[]).concat(room.extraProps)){
          const c=L.components[p.c],b=typeof c?.bounds==='function'?c.bounds(p.props||{}):c?.bounds;if(!b)continue;
          const box=new THREE.Mesh(new THREE.BoxGeometry(b[0],.08,b[1]),new THREE.MeshBasicMaterial({color:K.col('teal'),wireframe:true,transparent:true,opacity:.5,depthTest:false}));
          box.position.set(p.at[0],.2,p.at[1]);box.rotation.y=p.rot||0;group.add(box);
        }
        L.resources.track(guides);
      },
      inspect:()=>({links:links.children.length,guides:guides.children.length})
    };
  };
})();
