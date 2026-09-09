'use strict';
(function(root){
 function create({url,onSocket,onOpen,onMessage,onDisconnect,WebSocket:Socket=root.WebSocket,setTimeout:later=root.setTimeout,clearTimeout:cancel=root.clearTimeout}){
  let socket=null,retry=null,probe=null,pulse=null,opening=null,stopped=false,delay=500;
  function clear(){for(const timer of [probe,pulse,opening])if(timer!==null)cancel(timer);probe=pulse=opening=null;}
  function schedule(){if(stopped||retry!==null)return;retry=later(()=>{retry=null;connect();},delay);delay=Math.min(delay*2,10000);}
  function drop(current,event={}){if(socket!==current)return;clear();socket=null;onDisconnect(event);try{current.close();}catch{}schedule();}
  function ping(){if(stopped||!socket||socket.readyState!==1||probe!==null)return;const current=socket;try{current.send(JSON.stringify({type:'ping'}));}catch{drop(current,{reason:'send failed'});return;}probe=later(()=>drop(current,{reason:'heartbeat timeout'}),8000);}
  function heartbeat(){pulse=later(()=>{pulse=null;ping();if(socket&&!stopped)heartbeat();},10000);}
  function connect(){
   if(stopped||socket&&(socket.readyState===0||socket.readyState===1))return;
   if(retry!==null){cancel(retry);retry=null;}
   const current=new Socket(url());socket=current;onSocket(current);
   opening=later(()=>drop(current,{reason:'connect timeout'}),15000);
   current.addEventListener('open',()=>{if(current!==socket||stopped)return;cancel(opening);opening=null;onOpen();heartbeat();});
   current.addEventListener('message',event=>{
    if(current!==socket||stopped)return;let message;try{message=JSON.parse(event.data);}catch{return;}
    if(message.type==='pong'){if(probe!==null)cancel(probe);probe=null;}
    if(message.type==='auth_ok')delay=500;
    if(message.type==='replaced'){stopped=true;if(retry!==null)cancel(retry);retry=null;clear();onMessage(message);drop(current,{code:4000});return;}
    onMessage(message);
   });
   current.addEventListener('close',event=>{if(current!==socket)return;if(event.code===4000)stopped=true;drop(current,event);});
  }
  function resume(){if(stopped)return;if(!socket||socket.readyState>1)connect();else ping();}
  return {connect,resume};
 }
 const api={create};if(typeof module==='object'&&module.exports)module.exports=api;else root.ClientConnection=api;
})(globalThis);
