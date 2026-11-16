import QtQuick
import QtQuick.Window

Item {
    id: root
    property string mode: "idle"
    property real level: 0
    property real phase: 0
    property color tint: "#39eeff"
    implicitWidth: 500
    implicitHeight: 500
    onLevelChanged: scene.requestPaint()
    onModeChanged: scene.requestPaint()
    Timer {
        interval: 50
        running: root.visible && (!root.Window.window || (root.Window.window.visible && root.Window.window.visibility !== Window.Minimized))
        repeat: true
        onTriggered: { root.phase += root.mode === "thinking" ? 0.025 : 0.009; scene.requestPaint() }
    }
    Canvas {
        id: scene
        anchors.fill: parent
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            const c=getContext("2d"), s=Math.min(width,height), x=width/2, y=height*0.44, t=root.phase;
            const r=s*(0.267+root.level*0.012), tau=Math.PI*2;
            c.reset(); c.clearRect(0,0,width,height);
            let spectrum=c.createLinearGradient(x-r,y+r,x+r,y-r);
            spectrum.addColorStop(0,"#20edff"); spectrum.addColorStop(0.36,"#2c83ff"); spectrum.addColorStop(0.72,"#b335ff"); spectrum.addColorStop(1,"#ff8aff");
            function halo(cx,cy,radius,color) {
                let g=c.createRadialGradient(cx,cy,0,cx,cy,radius);
                g.addColorStop(0,color); g.addColorStop(1,"transparent");
                c.fillStyle=g; c.fillRect(0,0,width,height);
            }
            halo(x,y,s*0.49,"#132a6d"); halo(x+r*0.8,y-r*0.5,r,"#422068");
            function arc(radius,start,end,color,line) {
                c.beginPath(); c.arc(x,y,radius,start,end); c.strokeStyle=color; c.lineWidth=line; c.stroke();
            }
            arc(s*0.432,0,tau,"#103b67",1); arc(s*0.39,0,tau,"#174179",1); arc(s*0.347,0,tau,"#126c9c",1);
            for(let i=0;i<120;i++) {
                let a=i*tau/120, outer=s*0.397, inner=outer-(i%5===0?7:3);
                c.beginPath(); c.moveTo(x+Math.cos(a)*inner,y+Math.sin(a)*inner); c.lineTo(x+Math.cos(a)*outer,y+Math.sin(a)*outer);
                c.strokeStyle=i>65&&i<92?"#bd4aff":i%5===0?"#31d5f5":"#165578"; c.lineWidth=i%5===0?1.5:1; c.stroke();
            }
            for(let i=0;i<4;i++) {
                let a=t*0.22+i*Math.PI/2;
                arc(s*0.366,a,a+0.56,i%2?"#22cfe9":"#d352f9",6);
                arc(s*0.429,-a,-a+0.7,i%2?"#25729c":"#49429c",1);
            }
            let fill=c.createRadialGradient(x-r*0.4,y-r*0.45,r*0.05,x,y,r*1.1);
            fill.addColorStop(0,"#06365c"); fill.addColorStop(0.5,"#07133a"); fill.addColorStop(1,"#14124c");
            c.beginPath(); c.arc(x,y,r,0,tau); c.fillStyle=fill; c.fill();
            function project(lat,lon) {
                let px=Math.cos(lat)*Math.cos(lon+t*0.27)*r, pz=Math.cos(lat)*Math.sin(lon+t*0.27)*r, py=Math.sin(lat)*r;
                return {x:x+px,y:y+py*0.98-pz*0.18,z:py*0.18+pz*0.98};
            }
            function segment(a,b) {
                c.beginPath(); c.moveTo(a.x,a.y); c.lineTo(b.x,b.y);
                c.strokeStyle=spectrum; c.globalAlpha=0.08+Math.max(0,(a.z+b.z)/(2*r))*0.55; c.lineWidth=0.7; c.stroke();
            }
            for(let row=-10;row<=10;row++) {
                let lat=row*Math.PI/23, prev=project(lat,0);
                for(let col=1;col<=64;col++) { let next=project(lat,col*tau/64); segment(prev,next); prev=next; }
            }
            for(let col=0;col<30;col++) {
                let lon=col*tau/30, prev=project(-Math.PI/2,lon);
                for(let row=1;row<=32;row++) { let next=project(-Math.PI/2+row*Math.PI/32,lon); segment(prev,next); prev=next; }
            }
            c.globalAlpha=1;
            for(let row=-8;row<=8;row++) for(let col=0;col<28;col++) {
                let p=project(row*Math.PI/20,col*tau/28);
                if(p.z>0) { c.fillStyle=col%3===0?"#f4b8ff":"#83e9ff"; c.globalAlpha=0.2+p.z/r*0.65; c.fillRect(p.x,p.y,1.2,1.2); }
            }
            c.globalAlpha=1;
            c.save(); c.beginPath(); c.arc(x,y,r,0,tau); c.clip();
            let wave=c.createLinearGradient(x-r,0,x+r,0);
            wave.addColorStop(0,"#36ffec"); wave.addColorStop(0.3,"#ffb4ff"); wave.addColorStop(0.53,"#ed49ff"); wave.addColorStop(0.75,"#53e7ff"); wave.addColorStop(1,"#cc9bff");
            function wavePath(offset) {
                c.beginPath();
                for(let i=0;i<=100;i++) {
                    let u=-1+i/50, xx=x+u*r, yy=y-Math.sin(u*2.5+t*0.3)*r*0.43+offset*r+Math.cos(u*3)*r*0.1;
                    if(i===0)c.moveTo(xx,yy);else c.lineTo(xx,yy);
                }
            }
            for(let k=7;k>=0;k--) { wavePath(0.05); c.strokeStyle=wave; c.lineWidth=3+k*5; c.globalAlpha=k===0?1:0.08; c.stroke(); }
            for(let j=-5;j<=5;j++) { wavePath(j*0.027+0.05); c.strokeStyle=j===0?"#f3fbff":wave; c.lineWidth=j===0?2:0.8; c.globalAlpha=0.85-Math.abs(j)*0.08; c.stroke(); }
            c.restore();
            for(let k=5;k>=1;k--) { c.globalAlpha=0.08; arc(r,0,tau,spectrum,k*4); }
            c.globalAlpha=1; arc(r,0,tau,"#8deeff",1.6);
            const base=height*0.86;
            let beam=c.createLinearGradient(0,y+r*0.6,0,base);
            beam.addColorStop(0,"transparent"); beam.addColorStop(0.88,"rgba(183,106,255,0.38)"); beam.addColorStop(1,"rgba(150,250,255,0.8)");
            c.beginPath(); c.moveTo(x-r*0.65,y+r*0.7); c.lineTo(x+r*0.65,y+r*0.7); c.lineTo(x+r*0.13,base); c.lineTo(x-r*0.13,base); c.closePath(); c.fillStyle=beam; c.fill();
            for(let i=-4;i<=4;i++) { c.beginPath(); c.moveTo(x+i*r*0.14,y+r*0.8); c.lineTo(x+i*r*0.025,base); c.strokeStyle="rgba(146,156,255,0.22)"; c.lineWidth=1; c.stroke(); }
            halo(x,base,s*0.24,"#492b77");
            for(let i=6;i>=1;i--) {
                let rx=s*(0.07+i*0.036), ry=s*(0.009+i*0.006);
                c.beginPath(); c.ellipse(x-rx,base-ry,rx*2,ry*2); c.strokeStyle=i%2?"#34dfff":"#9d4eff"; c.lineWidth=i===5?2.5:1; c.stroke();
            }
            halo(x,base,s*0.09,"#a3c9ff");
            c.beginPath(); c.ellipse(x-s*0.065,base-s*0.009,s*0.13,s*0.018); c.strokeStyle="#e4ffff"; c.lineWidth=2; c.stroke();
            let flare=c.createLinearGradient(0,0,width,0);
            flare.addColorStop(0,"transparent"); flare.addColorStop(0.5,"#62eaff"); flare.addColorStop(1,"transparent");
            c.fillStyle=flare; c.fillRect(0,y+r*0.05,width,1); c.fillRect(0,base,width,1);
        }
    }
}
