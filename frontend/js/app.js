(function() {
  // ===== 手动求解逻辑 =====
  var dropZone    = document.getElementById('drop-zone');
  var fileInput   = document.getElementById('file-input');
  var placeholder = document.getElementById('placeholder');
  var preview     = document.getElementById('preview');
  var clearBtn    = document.getElementById('clear-btn');
  var solveBtn    = document.getElementById('solve-btn');
  var resultImg   = document.getElementById('result-img');
  var outputMsg   = document.getElementById('output-msg');
  var outputErr   = document.getElementById('output-error');
  var outputPH    = document.getElementById('output-placeholder');
  var overlay     = document.getElementById('overlay');
  var overlayImg  = document.getElementById('overlay-img');

  var currentImageBase64 = null;

  function loadImage(file) {
    if (!file || !file.type.startsWith('image/')) return;
    var reader = new FileReader();
    reader.onload = function(e) {
      currentImageBase64 = e.target.result;
      preview.src = currentImageBase64;
      preview.style.display = 'block';
      placeholder.style.display = 'none';
      dropZone.classList.add('has-image');
      solveBtn.disabled = false;
      resultImg.style.display = 'none';
      outputMsg.style.display = 'none';
      outputErr.style.display = 'none';
      outputPH.style.display = '';
    };
    reader.readAsDataURL(file);
  }

  dropZone.addEventListener('click', function(e) {
    if (e.target === clearBtn || clearBtn.contains(e.target)) return;
    if (!currentImageBase64) fileInput.click();
  });

  fileInput.addEventListener('change', function() {
    if (this.files && this.files[0]) loadImage(this.files[0]);
  });

  clearBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    currentImageBase64 = null;
    preview.style.display = 'none';
    preview.src = '';
    placeholder.style.display = '';
    dropZone.classList.remove('has-image');
    solveBtn.disabled = true;
    fileInput.value = '';
  });

  dropZone.addEventListener('dragover', function(e) {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });

  dropZone.addEventListener('dragleave', function() {
    dropZone.classList.remove('drag-over');
  });

  dropZone.addEventListener('drop', function(e) {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      loadImage(e.dataTransfer.files[0]);
    }
  });

  document.addEventListener('paste', function(e) {
    if (serverDisconnected) return;
    var items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (var i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        e.preventDefault();
        loadImage(items[i].getAsFile());
        break;
      }
    }
  });

  solveBtn.addEventListener('click', function() {
    if (!currentImageBase64 || serverDisconnected) return;
    solveBtn.disabled = true;
    solveBtn.innerHTML = '<span class="spinner"></span>正在求解...';
    outputPH.style.display = 'none';
    resultImg.style.display = 'none';
    outputMsg.style.display = 'none';
    outputErr.style.display = 'none';

    fetch('/solve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image: currentImageBase64 })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      if (data.success) {
        resultImg.src = 'data:image/png;base64,' + data.image;
        resultImg.style.display = 'block';
        outputMsg.textContent = data.message;
        outputMsg.style.display = 'block';
      } else {
        outputErr.textContent = data.message;
        outputErr.style.display = 'block';
        outputPH.style.display = '';
      }
    })
    .catch(function() {
      outputErr.textContent = '网络错误：无法连接到服务器';
      outputErr.style.display = 'block';
      outputPH.style.display = '';
      handleDisconnect();
    })
    .finally(function() {
      solveBtn.disabled = false;
      solveBtn.textContent = '开始求解';
    });
  });

  resultImg.addEventListener('click', function() {
    overlayImg.src = resultImg.src;
    overlay.classList.add('show');
  });

  overlay.addEventListener('click', function() {
    overlay.classList.remove('show');
  });

  // ===== 自动求解逻辑 =====
  var btnStart     = document.getElementById('btn-start');
  var btnPause     = document.getElementById('btn-pause');
  var btnStartIcon = document.getElementById('btn-start-icon');
  var btnStartText = document.getElementById('btn-start-text');
  var btnPauseIcon = document.getElementById('btn-pause-icon');
  var btnPauseText = document.getElementById('btn-pause-text');
  var statusDot    = document.getElementById('status-dot');
  var statusLabel  = document.getElementById('status-label');
  var statLevels   = document.getElementById('stat-levels');
  var statPlaced   = document.getElementById('stat-placed');
  var logContainer = document.getElementById('auto-log');

  // 截图区域相关元素
  var paramMonitor    = document.getElementById('param-monitor');
  var btnSelectRegion = document.getElementById('btn-select-region');
  var btnPreviewRegion = document.getElementById('btn-preview-region');
  var regionPreview   = document.getElementById('region-preview');
  var regionPreviewImg = document.getElementById('region-preview-img');
  var previewClose    = document.getElementById('preview-close');

  var autoStatus = 'idle';
  var serverDisconnected = false;  // 服务器是否已断连（页面失效）
  var logEntries = [];
  var logSyncIndex = 0;  // 与服务端日志同步的索引，避免裁剪后丢失日志
  var pollTimer  = null;
  var sseSource  = null;
  var monitorsData = [];    // 缓存显示器列表
  var selectedRegion = null;  // 框选结果（由框选按钮设置）

  // ===== 显示器列表 & 截图区域管理 =====

  // 页面加载时获取显示器列表
  function loadMonitors() {
    fetch('/auto/monitors')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.success && data.monitors) {
          monitorsData = data.monitors;
          paramMonitor.innerHTML = '';
          // 跳过 index=0（虚拟桌面），只显示物理显示器
          var hasMultiple = data.monitors.length > 2; // >2 意味着有多个物理显示器
          for (var i = 0; i < data.monitors.length; i++) {
            var mon = data.monitors[i];
            if (mon.index === 0) continue; // 跳过虚拟桌面
            var opt = document.createElement('option');
            opt.value = mon.index;
            opt.textContent = mon.name +
              ' (' + mon.left + ', ' + mon.top + ')';
            paramMonitor.appendChild(opt);
          }
          // 默认选第一个物理显示器
          if (monitorsData.length > 1) {
            paramMonitor.value = monitorsData[1].index;
          }
        }
      })
      .catch(function() {
        paramMonitor.innerHTML = '<option value="1">主显示器</option>';
      });
  }

  // 显示器下拉框切换时清除之前框选的区域
  paramMonitor.addEventListener('change', function() {
    selectedRegion = null;
    hideRegionPreview();
  });

  // 框选区域按钮
  btnSelectRegion.addEventListener('click', function() {
    if (serverDisconnected) return;
    var monitorIndex = parseInt(paramMonitor.value) || 1;
    btnSelectRegion.disabled = true;
    btnSelectRegion.innerHTML = '&#x23F3; 请在屏幕上框选...';

    fetch('/auto/select-region', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monitor_index: monitorIndex })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success && data.region) {
        selectedRegion = data.region;
        // 自动预览
        doPreviewRegion();
      } else {
        alert(data.message || '框选已取消');
      }
    })
    .catch(function(err) {
      alert('框选出错: ' + err.message);
    })
    .finally(function() {
      btnSelectRegion.disabled = false;
      btnSelectRegion.innerHTML = '&#x1F5BC; 框选区域';
    });
  });

  // 预览截图按钮
  btnPreviewRegion.addEventListener('click', function() {
    if (serverDisconnected) return;
    doPreviewRegion();
  });

  function doPreviewRegion() {
    var params = getRegionParams();
    if (params.width <= 0 || params.height <= 0) {
      alert('请先设置有效的截图区域');
      return;
    }
    btnPreviewRegion.disabled = true;
    fetch('/auto/preview-region', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success && data.image) {
        regionPreviewImg.src = 'data:image/png;base64,' + data.image;
        regionPreview.classList.add('has-preview');
      } else {
        alert(data.message || '预览失败');
      }
    })
    .catch(function(err) {
      alert('预览出错: ' + err.message);
    })
    .finally(function() {
      btnPreviewRegion.disabled = false;
    });
  }

  function hideRegionPreview() {
    regionPreview.classList.remove('has-preview');
  }

  previewClose.addEventListener('click', hideRegionPreview);

  function getRegionParams() {
    if (selectedRegion) {
      return {
        left: selectedRegion.left,
        top: selectedRegion.top,
        width: selectedRegion.width,
        height: selectedRegion.height
      };
    }
    // 未框选时返回空区域，getParams 会做校验
    return { left: 0, top: 0, width: 0, height: 0 };
  }

  // ===== 自动求解状态管理 =====

  function updateUI() {
    var isIdle = (autoStatus === 'idle' || autoStatus === 'completed' || autoStatus === 'error');
    // 所有非 idle/completed/error/paused 的状态都视为"运行中"
    var isActiveRunning = (!isIdle && autoStatus !== 'paused');
    var isActive = (!isIdle); // 包括 running/paused/所有子状态

    // 开始按钮：idle时显示"开始"，任何活跃状态（含暂停）显示"停止"
    if (isIdle) {
      btnStart.classList.remove('is-stop');
      btnStartIcon.innerHTML = '&#x25B6;';
      btnStartText.textContent = '开始';
      btnStart.disabled = false;
    } else {
      btnStart.classList.add('is-stop');
      btnStartIcon.innerHTML = '&#x25A0;';
      btnStartText.textContent = '停止';
      btnStart.disabled = false;
    }

    // 暂停按钮：只在活跃状态下可用
    btnPause.disabled = isIdle;
    if (autoStatus === 'paused') {
      btnPause.classList.add('is-resume');
      btnPauseIcon.innerHTML = '&#x25B6;';
      btnPauseText.textContent = '继续';
    } else {
      // running 及所有活跃子状态（capturing/solving/placing/waiting_*）
      btnPause.classList.remove('is-resume');
      btnPauseIcon.innerHTML = '&#x23F8;';
      btnPauseText.textContent = '暂停';
    }

    // 状态指示灯
    statusDot.className = 'status-dot';
    if (autoStatus === 'paused') {
      statusDot.classList.add('paused');
      statusLabel.textContent = '已暂停';
    } else if (autoStatus === 'error') {
      statusDot.classList.add('error');
      statusLabel.textContent = '出错';
    } else if (autoStatus === 'completed') {
      statusDot.classList.add('completed');
      statusLabel.textContent = '已完成';
    } else if (isActive) {
      statusDot.classList.add('running');
      // 按子状态显示更详细的文字
      var statusTextMap = {
        'running': '运行中',
        'capturing': '截图中',
        'solving': '求解中',
        'placing': '放置中',
        'waiting_load': '等待加载',
        'waiting_transition': '等待转场'
      };
      statusLabel.textContent = statusTextMap[autoStatus] || '运行中';
    } else {
      statusLabel.textContent = '就绪';
    }
  }

  function addLog(msg) {
    logEntries.push(msg);
    var cls = 'log-info';
    if (msg.indexOf('---') === 0) cls = 'log-level';
    else if (msg.indexOf('完成') !== -1 || msg.indexOf('已通过') !== -1) cls = 'log-success';
    else if (msg.indexOf('放置') !== -1) cls = 'log-action';
    else if (msg.indexOf('错误') !== -1 || msg.indexOf('失败') !== -1 || msg.indexOf('无法') !== -1) cls = 'log-error';
    else if (msg.indexOf('⏸') !== -1 || msg.indexOf('⏹') !== -1 || msg.indexOf('▶') !== -1) cls = 'log-status';
    else if (msg.indexOf('等待') !== -1 || msg.indexOf('暂停') !== -1 || msg.indexOf('停止') !== -1) cls = 'log-warning';

    var div = document.createElement('div');
    div.className = 'log-entry ' + cls;
    div.textContent = msg;
    logContainer.appendChild(div);
    logContainer.scrollTop = logContainer.scrollHeight;
  }

  function clearLog() {
    logEntries = [];
    logSyncIndex = 0;
    logContainer.innerHTML = '';
  }

  function getParams() {
    var region = getRegionParams();
    return {
      region_left: region.left,
      region_top: region.top,
      region_width: region.width,
      region_height: region.height,
      load_wait: 3.0,
      transition_wait: 3.0,
      max_levels: parseInt(document.getElementById('param-max-levels').value) || 9999
    };
  }

  var _disconnectWarned = false;  // 是否已提示过断连

  function handleDisconnect() {
    // 服务器断连：停止轮询、禁用所有交互、弹出遮罩
    if (serverDisconnected) return;
    serverDisconnected = true;
    stopPolling();

    // 禁用所有按钮
    solveBtn.disabled = true;
    btnStart.disabled = true;
    btnPause.disabled = true;
    btnSelectRegion.disabled = true;
    btnPreviewRegion.disabled = true;
    dropZone.style.pointerEvents = 'none';

    // 弹出断连遮罩
    document.getElementById('disconnect-overlay').style.display = 'flex';
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    _disconnectWarned = false;
    pollTimer = setInterval(function() {
      fetch('/auto/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          // 恢复连接
          if (_disconnectWarned) {
            _disconnectWarned = false;
            addLog('已重新连接到服务器');
            statusDot.className = 'status-dot';
            statusLabel.textContent = '';
          }

          var newStatus = data.status;
          if (newStatus !== autoStatus) {
            autoStatus = newStatus;
            updateUI();
          }

          // 求解器空闲/完成/出错时自动停止轮询，节省 CPU
          var isTerminal = (autoStatus === 'idle' || autoStatus === 'completed' || autoStatus === 'error');
          if (isTerminal) {
            // 先同步最后一批日志再停止
            statLevels.innerHTML = '&#x1F3AE; 已通关: <b>' + (data.level_completed || 0) + '</b>';
            statPlaced.innerHTML = '&#x1F404; 已放置: <b>' + (data.total_placed || 0) + '</b>';
            if (data.log && data.log.length > logSyncIndex) {
              for (var i = logSyncIndex; i < data.log.length; i++) {
                var entry = data.log[i];
                var msg = Array.isArray(entry) ? entry[1] : entry;
                addLog(msg);
              }
              logSyncIndex = data.log.length;
            }
            stopPolling();
            return;
          }

          statLevels.innerHTML = '&#x1F3AE; 已通关: <b>' + (data.level_completed || 0) + '</b>';
          statPlaced.innerHTML = '&#x1F404; 已放置: <b>' + (data.total_placed || 0) + '</b>';

          if (data.log && data.log.length > logSyncIndex) {
            for (var i = logSyncIndex; i < data.log.length; i++) {
              var entry = data.log[i];
              var msg = Array.isArray(entry) ? entry[1] : entry;
              addLog(msg);
            }
            logSyncIndex = data.log.length;
          } else if (data.log && data.log.length < logSyncIndex) {
            logSyncIndex = data.log.length;
          }
        })
        .catch(function() {
          handleDisconnect();
        });
    }, 500);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  // 开始/停止按钮
  btnStart.addEventListener('click', function() {
    if (serverDisconnected) return;

    var isIdle = (autoStatus === 'idle' || autoStatus === 'completed' || autoStatus === 'error');

    if (isIdle) {
      // 必须先框选区域
      if (!selectedRegion) {
        alert('请先点击「框选区域」选择游戏截图区域');
        return;
      }
      var params = getParams();
      clearLog();
      addLog('正在启动自动求解...');

      fetch('/auto/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.success) {
          addLog('启动失败: ' + data.message);
          autoStatus = 'error';
          updateUI();
          stopPolling();
        } else {
          autoStatus = 'running';
          updateUI();
          startPolling();
        }
      })
      .catch(function(err) {
        addLog('网络错误: ' + err.message);
        autoStatus = 'error';
        updateUI();
      });

    } else {
      // 立即禁用按钮，防止重复点击
      btnStart.disabled = true;
      btnPause.disabled = true;
      fetch('/auto/stop', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          addLog(data.message);
          // 轮询会自动检测到 idle 并更新状态
        })
        .catch(function() {})
        .finally(function() {
          // 恢复按钮（轮询会同步真实状态）
          btnStart.disabled = false;
        });
    }
  });

  // 暂停/继续按钮
  btnPause.addEventListener('click', function() {
    if (serverDisconnected) return;
    // 立即禁用按钮防止重复点击
    btnPause.disabled = true;
    fetch('/auto/pause', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.success) {
          // 立即更新状态，不等轮询
          autoStatus = data.status;
          updateUI();
          addLog(data.message);
        } else {
          addLog('操作失败: ' + data.message);
          btnPause.disabled = false;
        }
      })
      .catch(function() {
        btnPause.disabled = false;
      });
  });

  // 初始化
  loadMonitors();
  updateUI();

  // 刷新按钮（断连遮罩上）
  document.getElementById('disconnect-refresh').addEventListener('click', function() {
    location.reload();
  });
})();
