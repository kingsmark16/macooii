import QtQuick

Canvas {
    id: canvas
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const c = getContext("2d"), w = width, h = height;
        c.reset(); c.fillStyle = "#030a20"; c.fillRect(0, 0, w, h);
        function glow(x, y, r, color) {
            let g = c.createRadialGradient(x,y,0,x,y,r);
            g.addColorStop(0,color); g.addColorStop(1,"transparent");
            c.fillStyle=g; c.fillRect(0,0,w,h);
        }
        glow(w*0.52,h*0.35,w*0.47,"#0c1841");
        glow(w*0.10,h*0.62,w*0.32,"#081f3b");
        glow(w*0.92,h*0.23,w*0.28,"#1d1047");
        // Perspective floor beneath the hologram.
        const horizon=h*0.49, floor=h*0.72, cx=w*0.52;
        c.lineWidth=0.7;
        for(let i=-18;i<=18;i++) {
            c.strokeStyle=i%3===0?"#144c75":"#0b2947";
            c.beginPath(); c.moveTo(cx+i*12,horizon); c.lineTo(cx+i*78,floor); c.stroke();
        }
        for(let i=0;i<11;i++) {
            let p=i/10, y=horizon+(floor-horizon)*p*p;
            c.strokeStyle="rgba(17,122,180,"+(0.12+p*0.24)+")";
            c.beginPath(); c.moveTo(w*0.16,y); c.lineTo(w*0.87,y); c.stroke();
        }
        function ribbon(base, amplitude, phase, alpha, layers) {
            let g=c.createLinearGradient(0,0,w,0);
            g.addColorStop(0,"#6526fe"); g.addColorStop(0.2,"#ee39ff");
            g.addColorStop(0.51,"#1af4ff"); g.addColorStop(0.78,"#2560ff"); g.addColorStop(1,"#d72eff");
            for(let j=layers;j>=0;j--) {
                c.beginPath();
                for(let x=0;x<=w;x+=5) {
                    let y=base+Math.sin(x/w*8+phase)*amplitude + Math.sin(x/w*15+phase)*amplitude*0.2;
                    if(x===0)c.moveTo(x,y);else c.lineTo(x,y);
                }
                c.strokeStyle=g; c.lineWidth=j===0?1.5:j*6;
                c.globalAlpha=j===0?alpha:alpha*0.065; c.stroke();
            }
            c.globalAlpha=1;
        }
        ribbon(h*0.95,h*0.033,2,0.95,9);
        ribbon(h*0.48,h*0.16,0.8,0.32,5);
        ribbon(h*0.075,h*0.065,0.1,0.28,4);
        // Fine, receding particle mesh along the bottom energy wave.
        for(let row=0;row<19;row++) for(let col=0;col<190;col++) {
            let x=col*w/189, y=h*0.95+Math.sin(x/w*8+2)*h*0.033+Math.sin(x/w*15+2)*h*0.0066+row*2.7;
            c.fillStyle=col%4===0?"#6a5cff":"#187dba"; c.globalAlpha=(1-row/20)*0.65;
            c.fillRect(x,y,1,1);
        }
        c.globalAlpha=1;
        for(let i=0;i<85;i++) {
            c.fillStyle=i%4===0?"#257293":"#182a57";
            c.fillRect((i*193+57)%w,(i*89+25)%(h*0.85),1,1);
        }
    }
}
