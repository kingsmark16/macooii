import QtQuick
Canvas {
    id: root
    property string kind: "Voice"
    property color tint: "#80d7ed"
    width: 24; height: 24
    onTintChanged: requestPaint()
    onKindChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const c = getContext("2d"); c.reset(); c.clearRect(0,0,width,height)
        c.scale(width/24,height/24)
        c.strokeStyle = tint; c.lineWidth = 1.3; c.lineCap = "round"; c.lineJoin = "round"
        function line(x1,y1,x2,y2) { c.beginPath(); c.moveTo(x1,y1); c.lineTo(x2,y2); c.stroke() }
        if (kind === "Voice") {
            c.beginPath(); c.roundedRect(9,2,6,13,3,3); c.stroke()
            c.beginPath(); c.arc(12,11,7,0,Math.PI); c.stroke()
            line(5,10,5,12); line(19,10,19,12); line(12,18,12,22); line(8,22,16,22)
        } else if (kind === "Notes") {
            c.strokeRect(5,3,14,18); line(8,8,16,8); line(8,12,16,12); line(8,16,13,16)
        } else if (kind === "Memory") {
            for(let i=0;i<3;i++) { c.beginPath(); c.moveTo(3,7+i*5); c.lineTo(12,2+i*5); c.lineTo(21,7+i*5); c.lineTo(12,12+i*5); c.closePath(); c.stroke() }
        } else if (kind === "Bolt") {
            c.beginPath(); c.moveTo(14,1); c.lineTo(4,14); c.lineTo(11,14); c.lineTo(9,23); c.lineTo(21,9); c.lineTo(13,9); c.closePath(); c.stroke()
        } else if (kind === "Clock") {
            c.beginPath(); c.arc(12,12,9,0,Math.PI*2); c.stroke(); line(12,6,12,12); line(12,12,16,15)
        } else if (kind === "Chart") {
            c.strokeRect(3,13,4,8); c.strokeRect(10,7,4,14); c.strokeRect(17,2,4,19)
        } else if (kind === "Focus") {
            c.beginPath(); c.arc(12,12,9,0,Math.PI*2); c.stroke(); c.beginPath(); c.arc(12,12,5,0,Math.PI*2); c.stroke(); line(12,12,22,2)
        } else if (kind === "Chat") {
            c.beginPath(); c.moveTo(3,3); c.lineTo(21,3); c.lineTo(21,17); c.lineTo(10,17); c.lineTo(5,22); c.lineTo(5,17); c.lineTo(3,17); c.closePath(); c.stroke()
            for(let i=0;i<3;i++) { c.beginPath(); c.arc(7+i*5,10,0.7,0,Math.PI*2); c.stroke() }
        } else if (kind === "Send") {
            c.beginPath(); c.moveTo(2,8); c.lineTo(22,2); c.lineTo(15,22); c.lineTo(10,13); c.closePath(); c.stroke(); line(10,13,22,2)
        } else if (kind === "Activity") {
            c.beginPath(); c.moveTo(2,13); c.lineTo(6,13); c.lineTo(9,5); c.lineTo(13,20); c.lineTo(17,9); c.lineTo(20,13); c.lineTo(23,13); c.stroke()
        } else {
            c.beginPath(); c.arc(12,12,6,0,Math.PI*2); c.stroke()
            c.beginPath(); c.arc(12,12,2,0,Math.PI*2); c.stroke()
            for(let i=0;i<8;i++) { let a=i*Math.PI/4; line(12+Math.cos(a)*8,12+Math.sin(a)*8,12+Math.cos(a)*10,12+Math.sin(a)*10) }
        }
    }
}
