const $ = (s) => document.querySelector(s);
const show = (id) => ['choose','remote','local'].forEach(k => $('#'+k).classList.toggle('hide', k !== id));

(async () => {
  const conf = await window.coco.getConf();
  $('#status').textContent = conf.mode === 'remote' ? '已连接服务器' : (conf.mode === 'local' ? '本机模式' : '未连接');
})();

$('#m1').onclick = () => show('remote');
$('#m2').onclick = () => show('local');
$('#back1').onclick = $('#back2').onclick = () => show('choose');

$('#save1').onclick = async () => {
  const url = $('#url').value.trim(), token = $('#token').value.trim();
  if (!url) { alert('请填写服务器地址'); return; }
  await window.coco.setConf({ mode: 'remote', url, token });
  $('#status').textContent = '已连接服务器';
  alert('已保存。连接与验证会在下一步实现。');
};

$('#go').onclick = async () => {
  await window.coco.setConf({ mode: 'local' });
  // 安装流程由主进程实现（下一步），这里先演示进度反馈
  for (const li of document.querySelectorAll('#steps li')) {
    li.classList.add('doing');
    await new Promise(r => setTimeout(r, 700));
    li.classList.remove('doing'); li.classList.add('done');
  }
  $('#status').textContent = '本机模式';
};
