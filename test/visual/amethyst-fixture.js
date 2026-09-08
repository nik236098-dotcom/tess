// Local browser QA only. Never loaded by index.html or production app.js.
// These are representative states; the real WebSocket path is tested separately.
const qaNames=['PokerGena','Emma','Daniel','Lucas','Sophia','Mina','Rafael','Chris'];
const qaPortraits=[[323,1089,122],[59,881,94],[33,588,94],[62,318,94],[337,184,94],[614,318,94],[638,588,94],[614,881,94]];
state.user={id:'qa:hero',name:'PokerGena'};state.isAdmin=true;state.connected=true;
state.socket={readyState:1,send(text){document.body.dataset.lastCommand=text;}};
const qaRoom={type:'state',code:'DEMO',game:'holdem',title:'PokerGena',settings:{game:'holdem',smallBlind:50,bigBlind:100,minBuyIn:500,buyIn:10000,maxPlayers:8,turnSeconds:180},running:true,handNumber:3,phase:'river',status:'playing',board:['Qh','Js','7h','9s','2d'],pot:2400,potTotal:4800,turnDeadline:Date.now()+180000,lastResult:null,feed:[],log:[],spectators:[],
seats:qaNames.map((name,index)=>({index,empty:false,userId:index?'qa:'+index:'qa:hero',name,photoUrl:null,stack:[13500,12000,9100,8700,10250,6425,7650,5875][index],cards:index?['??','??']:['As','Kh'],connected:true,inHand:true,folded:index===2,bet:[400,200,0,200,400,400,100,100][index],isActing:index===0,combination:index===0?'Старшая A':null})),
you:{userId:'qa:hero',seatIndex:0,isHost:true,balance:40000,stack:13500,canStart:false,canRebuy:false,buyIn:{min:500,max:40000,default:10000,enough:true},legal:{canFold:true,canCheck:false,canCall:true,callAmount:400,canRaise:true,canAllIn:true,minRaiseTo:800,maxRaiseTo:13900}}};
state.room=qaRoom;showTable();renderTable();fitTable();
const qaCss=document.createElement('style');qaCss.textContent=qaPortraits.map(([x,y,d],i)=>`.am-seat[data-seat="${i}"] .am-avatar{background:url('/img/amethyst/art.webp') -${x}px -${y}px/768px 1536px no-repeat}.am-seat[data-seat="${i}"] .am-avatar svg{display:none}`).join('');document.head.append(qaCss);
const qaToolbar=document.createElement('div');qaToolbar.id='qa-toolbar';qaToolbar.style='position:fixed;top:74px;left:85px;max-width:220px;z-index:999;background:#160b21';
qaToolbar.innerHTML='<button id="qa-holdem">Холдем 8</button><button id="qa-omaha">Омаха 8</button><button id="qa-empty">Свободное место</button><button id="qa-opponent">Ход соперника</button><button id="qa-hero">Ход героя</button>';
document.body.append(qaToolbar);
if (new URLSearchParams(location.search).has('clean')) qaToolbar.hidden = true;
$('qa-omaha').onclick=()=>{state.room.game='omaha';state.room.seats.forEach((s,i)=>s.cards=i?['??','??','??','??']:['As','Kh','Jc','Td']);renderTable();};
$('qa-holdem').onclick=()=>{state.room.game='holdem';state.room.seats.forEach((s,i)=>s.cards=i?['??','??']:['As','Kh']);renderTable();};
$('qa-empty').onclick=()=>{state.room.seats[3]={index:3,empty:true};renderTable();};
$('qa-opponent').onclick=()=>{state.room.seats[0].isActing=false;state.room.seats[5].isActing=true;state.room.you.legal=null;renderTable();};
$('qa-hero').onclick=()=>{state.room.seats[0].isActing=true;state.room.seats[5].isActing=false;state.room.you.legal=qaRoom.you.legal;renderTable();};
