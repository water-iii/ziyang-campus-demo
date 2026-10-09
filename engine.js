/* Campus Lunch Shuttle Demo - in-memory business engine, no external services. */
(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.DemoCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const merchants = [
    {id:'m1',name:'梅西·米饭研究所',zone:'梅西商圈',kind:'盖饭·简餐',symbol:'🍱',tone:'peach',pickup:'11:05',status:'虚拟演示商家'},
    {id:'m2',name:'梅西·香酥鸡厨房',zone:'梅西商圈',kind:'炸鸡·套餐',symbol:'🍗',tone:'amber',pickup:'11:15',status:'虚拟演示商家'},
    {id:'m3',name:'达高·川味小馆',zone:'达高商圈',kind:'川味·家常菜',symbol:'🥘',tone:'blue',pickup:'11:25',status:'虚拟演示商家'}
  ];
  const products = [
    {id:'p11',mid:'m1',name:'香菇鸡腿饭',price:18,desc:'招牌午餐 · 演示定价',symbol:'🍚'},
    {id:'p12',mid:'m1',name:'红烧牛肉饭',price:22,desc:'浓郁酱汁 · 演示定价',symbol:'🥩'},
    {id:'p13',mid:'m1',name:'双拼便当',price:24,desc:'双拼选择 · 演示定价',symbol:'🍱'},
    {id:'p21',mid:'m2',name:'香酥鸡腿套餐',price:20,desc:'密封包装 · 演示定价',symbol:'🍗'},
    {id:'p22',mid:'m2',name:'鸡米花盖饭',price:17,desc:'经典快餐 · 演示定价',symbol:'🍛'},
    {id:'p23',mid:'m2',name:'照烧鸡排饭',price:21,desc:'定时取货 · 演示定价',symbol:'🍖'},
    {id:'p31',mid:'m3',name:'宫保鸡丁饭',price:19,desc:'现制出餐 · 演示定价',symbol:'🥘'},
    {id:'p32',mid:'m3',name:'青椒肉丝盖饭',price:18,desc:'人气盖饭 · 演示定价',symbol:'🌶️'},
    {id:'p33',mid:'m3',name:'家常小炒套餐',price:23,desc:'下饭套餐 · 演示定价',symbol:'🍲'}
  ];
  const stops = merchants.map((m,i)=>({mid:m.id,sequence:i+1,pickup:m.pickup}));
  const points = ['指定交接点 A（演示）','指定交接点 B（演示）'];
  const stateLabels = {open:'开放预订',cutoff:'已截单',collecting:'城区取货中',transit:'干线运输中',campus:'到校交接完成',delivering:'校园配送中',finished:'已结束'};
  const stamp = ()=> new Date().toLocaleString('zh-CN',{hour12:false});
  const clone = obj => JSON.parse(JSON.stringify(obj));
  const expect = (condition, message) => { if (!condition) throw new Error(message); };
  const money = value => '¥'+(Number(value)||0).toFixed(2);

  function addEvent(db,msg) {
    db.events.unshift({id: 'e'+Date.now().toString(36)+Math.random().toString(36).slice(2,6),time:stamp(),message:msg});
    db.events=db.events.slice(0,90);
  }
  function createSeed() {
    const orders=[]; const parcels=[];
    for(let i=0;i<30;i++) {
      const mid = i<12 ? 'm1' : (i<22 ? 'm2' : 'm3');
      const options=products.filter(p=>p.mid===mid);
      const product=options[i%3];
      const bags=[4,11,18,25].includes(i)?2:1;
      const order={id:'O'+(260801+i),mid,items:[{id:product.id,qty:bags,price:product.price,name:product.name}],point:points[i%2],accepted:false,paidDemo:true,studentName:'演示用户'+String(i+1).padStart(2,'0'),created:'10:'+String(i%40).padStart(2,'0'),mock:true};
      orders.push(order);
      for(let b=0;b<bags;b++) parcels.push({id:'P'+(260801+i)+'-'+(b+1),orderId:order.id,mid,state:'pending'});
    }
    return {
      schema:1, merchants:clone(merchants), products:clone(products), orders,parcels,
      batch:{id:'B001',school:'资阳环境科技职业学院',status:'open',cutoff:'10:40',depart:'11:30',eta:'12:10–12:30',maxOrders:60,day:'演示工作日'},
      route:{id:'R001',name:'梅西—达高城区取货线',stops:clone(stops)},
      pickupDone:{}, issues:[], events:[{id:'e-init',time:stamp(),message:'加载了30笔演示订单和34个餐袋；本班开放预订。'}],
      costs:{fee:2.5,commission:0.08,variable:2.05,fixed:90}, nextId:260831
    };
  }
  function findMerchant(db,mid) {return db.merchants.find(x=>x.id===mid);}
  function byMerchant(db,mid) {return db.orders.filter(x=>x.mid===mid);}
  function orderParcels(db,oid) {return db.parcels.filter(x=>x.orderId===oid);}
  function orderAmount(order) {return order.items.reduce((sum,x)=>sum+x.qty*x.price,0);}
  function orderStatus(db,order) {
    const bags=orderParcels(db,order.id);
    if(bags.some(x=>x.state==='missing')) return '取货异常';
    if(bags.every(x=>x.state==='refunded')) return '已模拟退款';
    if(bags.some(x=>x.state==='refunded')) return bags.every(x=>['refunded','delivered'].includes(x.state))?'部分退款完成':'部分异常';
    if(!order.accepted) return '待商家接单';
    const index={pending:0,ready:1,picked:2,campus:3,out:4,delivered:5};
    const min=Math.min(...bags.map(x=>index[x.state]??0));
    if(min===0) return '制作中';
    if(min===1) return '已打包待取';
    if(min===2) return ['transit','campus','delivering','finished'].includes(db.batch.status)?'干线运输中':'已装车';
    if(min===3) return '已到校交接点';
    if(min===4) return '末端配送中';
    return '已交付';
  }
  function totals(db) {
    const bags=db.parcels;
    const uniqueCount=db.orders.length;
    const foodAmount=db.orders.reduce((sum,o)=>sum+orderAmount(o),0);
    const refunded=db.orders.filter(o=>orderParcels(db,o.id).every(p=>p.state==='refunded'));
    const refundFood=refunded.reduce((sum,o)=>sum+orderAmount(o),0);
    const paidOrders=uniqueCount-refunded.length;
    const revenue=(foodAmount-refundFood)*db.costs.commission+paidOrders*db.costs.fee;
    const variable=uniqueCount*db.costs.variable;
    const fixed=db.costs.fixed;
    return {orders:uniqueCount,bags:bags.length,ready:bags.filter(x=>x.state==='ready').length,picked:bags.filter(x=>x.state==='picked').length,campus:bags.filter(x=>x.state==='campus').length,out:bags.filter(x=>x.state==='out').length,delivered:bags.filter(x=>x.state==='delivered').length,missing:bags.filter(x=>x.state==='missing').length,refunded:bags.filter(x=>x.state==='refunded').length,foodAmount,revenue,variable,fixed,contribution:revenue-variable-fixed,activeIssues:db.issues.filter(x=>x.status==='open').length};
  }
  function addStudentOrder(db,mid,cart,point) {
    expect(db.batch.status==='open','本班已截单，无法新增演示订单。');
    expect(db.orders.length<db.batch.maxOrders,'本班已达到演示容量上限。');
    expect(points.includes(point),'请选择预先配置的演示交接点。');
    expect(db.merchants.some(x=>x.id===mid),'商家不存在。');
    const items=Object.entries(cart).filter(([id,qty])=>Number(qty)>0).map(([id,qty])=>{
      const prod=db.products.find(x=>x.id===id && x.mid===mid);
      expect(prod,'购物车存在无效商品。');
      expect(Number.isInteger(qty)&&qty>0&&qty<=20,'商品数量不合法。');
      return {id,name:prod.name,price:prod.price,qty};
    });
    expect(items.length>0,'请先添加餐品。');
    const id='O'+db.nextId++;
    const order={id,mid,items,point,accepted:false,paidDemo:true,studentName:'演示新用户',created:stamp(),mock:true,isStudentDemo:true};
    db.orders.push(order);
    const bagCount=Math.max(1,Math.ceil(items.reduce((sum,x)=>sum+x.qty,0)/2));
    for(let i=0;i<bagCount;i++) db.parcels.push({id:'P'+id.slice(1)+'-'+(i+1),orderId:id,mid,state:'pending'});
    addEvent(db,'学生端提交模拟订单 '+id+'（'+findMerchant(db,mid).name+'，'+bagCount+'袋）');
    return id;
  }
  function cutoff(db) {
    expect(db.batch.status==='open','只有开放预订的班次可以截单。');
    db.batch.status='cutoff'; addEvent(db,'运营端确认截单；本班订单数 '+db.orders.length+'。');
  }
  function acceptMerchant(db,mid) {
    expect(db.batch.status==='cutoff' || db.batch.status==='collecting','请先截单，再确认商家出餐。');
    const orders=byMerchant(db,mid);
    expect(orders.length>0,'商家暂无订单。');
    for(const o of orders) o.accepted=true;
    addEvent(db,findMerchant(db,mid).name+' 已确认本班 '+orders.length+' 单。');
  }
  function packMerchant(db,mid) {
    expect(db.batch.status==='cutoff'||db.batch.status==='collecting','当前班次不能进行打包操作。');
    const orders=byMerchant(db,mid);
    expect(orders.every(x=>x.accepted),'请先确认该商家的全部订单。');
    expect(!db.pickupDone[mid],'该商家已发生取货交接，不能重新打包。');
    let count=0;
    for(const p of db.parcels.filter(x=>x.mid===mid && x.state==='pending')) {p.state='ready';count++;}
    expect(count>0,'本店没有待打包餐袋。');
    addEvent(db,findMerchant(db,mid).name+' 确认全部模拟餐袋打包完成（'+count+'袋）。');
  }
  function pickupMerchant(db,mid,shortage) {
    expect(['cutoff','collecting'].includes(db.batch.status),'当前班次不允许取货。');
    expect(!db.pickupDone[mid],'该商家已确认过交接。');
    const stopIndex=db.route.stops.findIndex(x=>x.mid===mid);
    expect(stopIndex>=0,'取货线路中不存在该商家。');
    for(let i=0;i<stopIndex;i++) expect(db.pickupDone[db.route.stops[i].mid],'请先完成上一站取货。');
    const storeBags=db.parcels.filter(x=>x.mid===mid);
    expect(storeBags.length>0,'商家没有餐袋。');
    expect(storeBags.every(x=>x.state==='ready'),'该商家存在未打包餐袋，请联系商家完成出餐。');
    if(shortage) {
      const chosen=storeBags.find(x=>orderParcels(db,x.orderId).length===1) || storeBags[0];
      chosen.state='missing';
      db.issues.unshift({id:'EX'+String(db.issues.length+1).padStart(3,'0'),parcelId:chosen.id,orderId:chosen.orderId,mid,type:'商家交接缺袋',status:'open',created:stamp(),resolution:''});
    }
    let count=0;
    for(const p of storeBags) if(p.state==='ready') {p.state='picked';count++;}
    db.pickupDone[mid]={picked:count,expected:storeBags.length,time:stamp()};
    db.batch.status='collecting';
    addEvent(db,findMerchant(db,mid).name+' 取货交接完成：应取'+storeBags.length+'袋，实取'+count+'袋'+(shortage?'，已登记缺袋异常':'')+'。');
  }
  function depart(db) {
    expect(db.batch.status==='collecting','请先完成城区取货。');
    expect(db.route.stops.every(x=>db.pickupDone[x.mid]),'还有商家未完成交接，不能发车。');
    expect(db.parcels.some(x=>x.state==='picked'),'未装载任何餐袋，不能确认发车。');
    db.batch.status='transit';addEvent(db,'司机确认11:30计划班次已模拟发车，实装'+db.parcels.filter(x=>x.state==='picked').length+'袋。');
  }
  function campusReceive(db) {
    expect(db.batch.status==='transit','请先确认车辆发车。');
    const bags=db.parcels.filter(x=>x.state==='picked');
    expect(bags.length>0,'当前无可接收的餐袋。');
    for(const p of bags) p.state='campus';
    db.batch.status='campus';addEvent(db,'校园负责人在模拟交接点清点接收 '+bags.length+'袋。');
  }
  function assignDelivery(db) {
    expect(db.batch.status==='campus','请先完成到校清点交接。');
    const bags=db.parcels.filter(x=>x.state==='campus');
    expect(bags.length>0,'没有可分派餐袋。');
    for(const p of bags) p.state='out';
    db.batch.status='delivering';addEvent(db,'校园负责人按演示交接点分配 '+bags.length+'袋，进入末端交付。');
  }
  function completeDelivery(db) {
    expect(db.batch.status==='delivering','请先分配配送任务。');
    const bags=db.parcels.filter(x=>x.state==='out');
    expect(bags.length>0,'没有待交付餐袋。');
    for(const p of bags) p.state='delivered';
    addEvent(db,'校园配送员模拟完成 '+bags.length+'袋交付。');
    updateFinished(db);
  }
  function updateFinished(db) {
    if(['delivering','finished'].includes(db.batch.status) && db.parcels.every(x=>['delivered','refunded'].includes(x.state)) && db.issues.every(x=>x.status==='resolved')) {
      db.batch.status='finished';
      addEvent(db,'本班所有餐袋均有最终处置结果，班次正式模拟结案。');
    }
  }
  function resolveIssue(db,issueId) {
    const issue=db.issues.find(x=>x.id===issueId);
    expect(issue && issue.status==='open','异常不存在或已经处理。');
    const parcel=db.parcels.find(x=>x.id===issue.parcelId);
    expect(parcel && parcel.state==='missing','此异常没有可退款的未装车餐袋。');
    parcel.state='refunded';issue.status='resolved';issue.resolution='模拟退款（无真实资金动作）';issue.resolvedAt=stamp();
    addEvent(db,'运营处理 '+issue.id+'：'+parcel.id+' 已标记为模拟退款。');
    updateFinished(db);
  }
  function changeFixedCost(db,value) {
    const n=Number(value);
    expect(Number.isFinite(n)&&n>=0&&n<=2000,'固定成本应为0～2000元。');
    db.costs.fixed=n;
  }
  return {merchants,products,points,stateLabels,money,createSeed,findMerchant,byMerchant,orderParcels,orderAmount,orderStatus,totals,addStudentOrder,cutoff,acceptMerchant,packMerchant,pickupMerchant,depart,campusReceive,assignDelivery,completeDelivery,resolveIssue,changeFixedCost};
});
