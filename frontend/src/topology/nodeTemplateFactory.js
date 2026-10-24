import go from 'gojs'
import routerImg from '../assets/netequip/icons/router.png'
import switchImg from '../assets/netequip/icons/switch-core.png'
import firewallImg from '../assets/netequip/icons/firewall.png'
import apImg from '../assets/netequip/icons/ap.png'
import serverImg from '../assets/netequip/icons/server.png'
import lbImg from '../assets/netequip/icons/lb.png'
import sdwanImg from '../assets/netequip/icons/sdwan.png'
import behaviorImg from '../assets/netequip/icons/behavior.png'

const $ = go.GraphObject.make

// ---- Port configuration per device type (used by LinkConfigDialog) ----
const PORT_SPECS = {
  router:       { count: 6, names: ['GE0/0/0', 'GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5'], ethTrunkNames: [] },
  switch:       { count: 10, names: ['GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5', 'GE0/0/6', 'GE0/0/7', 'GE0/0/8', 'GE0/0/9', 'GE0/0/10'], ethTrunkNames: ['Eth-Trunk1', 'Eth-Trunk2', 'Eth-Trunk3', 'Eth-Trunk4', 'Eth-Trunk5', 'Eth-Trunk6', 'Eth-Trunk7', 'Eth-Trunk8'] },
  firewall:     { count: 6, names: ['GE0/0/0', 'GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5'], ethTrunkNames: [] },
  ips:          { count: 6, names: ['GE0/0/0', 'GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5'], ethTrunkNames: [] },
  pc:           { count: 1, names: ['ETH0'], ethTrunkNames: [] },
  laptop:       { count: 1, names: ['ETH0'], ethTrunkNames: [] },
  server:       { count: 2, names: ['ETH0', 'ETH1'], ethTrunkNames: [] },
  phone:        { count: 1, names: ['ETH0'], ethTrunkNames: [] },
  camera:       { count: 1, names: ['ETH0'], ethTrunkNames: [] },
  nvr:          { count: 2, names: ['ETH0', 'ETH1'], ethTrunkNames: [] },
  printer:      { count: 1, names: ['ETH0'], ethTrunkNames: [] },
  'dumb-switch':{ count: 8, names: ['GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5', 'GE0/0/6', 'GE0/0/7', 'GE0/0/8'], ethTrunkNames: [] },
  ap:           { count: 1, names: ['ETH0'], ethTrunkNames: [] },
  ac:           { count: 4, names: ['GE0/0/0', 'GE0/0/1', 'GE0/0/2', 'GE0/0/3'], ethTrunkNames: [] },
  lb:           { count: 6, names: ['GE0/0/0', 'GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5'], ethTrunkNames: [] },
  sdwan:        { count: 6, names: ['GE0/0/0', 'GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5'], ethTrunkNames: [] },
  behavior:     { count: 6, names: ['GE0/0/0', 'GE0/0/1', 'GE0/0/2', 'GE0/0/3', 'GE0/0/4', 'GE0/0/5'], ethTrunkNames: [] },
  cloud:        { count: 3, names: ['ETH0', 'ETH1', 'ETH2'], ethTrunkNames: [] },
}

// ---- Reusable helpers ----

function slotRect(w, h) {
  return $(go.Shape, 'Rectangle', {
    width: w || 14, height: h || 6,
    fill: '#37474F', stroke: '#263238',
    strokeWidth: 1,
    margin: new go.Margin(0, 2, 0, 0),
  })
}

function led(color) {
  return $(go.Shape, 'Circle', {
    width: 4, height: 4,
    fill: color, stroke: '#555',
    margin: new go.Margin(0, 2),
  })
}

function portInd() {
  return $(go.Shape, 'Rectangle', {
    width: 7, height: 4,
    fill: '#B0BEC5', stroke: '#78909C',
    strokeWidth: 0.5,
    margin: new go.Margin(0, 1.5),
  })
}

function linkableBody(shape, portId) {
  shape.portId = portId || ''
  shape.fromLinkable = true
  shape.toLinkable = true
  shape.cursor = 'crosshair'
}

function labelBlock() {
  // 设备名 + 管理 IP 两行 (工程交付规范: IP 标注在设备旁)
  return $(go.Panel, 'Vertical',
    {
      alignment: go.Spot.BottomCenter,
      alignmentFocus: go.Spot.TopCenter,
    },
    $(go.TextBlock, {
      margin: new go.Margin(4, 2, 0, 2),
      font: 'bold 11px "Microsoft YaHei", sans-serif',
      stroke: '#333',
      background: 'rgba(255,255,255,0.85)',
      editable: true,
      textAlign: 'center',
    }, new go.Binding('text', 'label').makeTwoWay()),
    $(go.TextBlock, {
      margin: new go.Margin(1, 2, 0, 2),
      font: '10px Consolas, monospace',
      stroke: '#546E7A',
      background: 'rgba(255,255,255,0.85)',
      visible: false,
      textAlign: 'center',
    },
      new go.Binding('text', 'mgmtIp'),
      new go.Binding('visible', 'mgmtIp', v => !!v)),
  )
}

// ---- eNSP/HCL 风格图标部件 ----

// 单个箭头: 矩形杆 + 三角头 (eNSP 交换机/路由器图标的核心元素)
function arrowGlyph(right) {
  const parts = []
  if (!right) parts.push($(go.Shape, 'Triangle', { width: 5, height: 8, angle: 270, fill: '#FFFFFF', stroke: null }))
  parts.push($(go.Shape, 'Rectangle', { width: 9, height: 2.5, fill: '#FFFFFF', stroke: null }))
  if (right) parts.push($(go.Shape, 'Triangle', { width: 5, height: 8, angle: 90, fill: '#FFFFFF', stroke: null }))
  return $(go.Panel, 'Horizontal', parts)
}

// 一排双向箭头 (eNSP 交换机: 上面板朝左, 下面板朝右)
function arrowRow(dir, count) {
  const parts = []
  for (let i = 0; i < count; i++) parts.push(arrowGlyph(dir > 0))
  return $(go.Panel, 'Horizontal', { margin: new go.Margin(2, 0) }, parts)
}

// 砖墙 (eNSP 防火墙图标)
function brickWall(rows, brickW, brickH) {
  const wall = []
  for (let r = 0; r < rows; r++) {
    const offset = r % 2 === 0 ? 0 : brickW / 2
    const line = []
    // 半砖开头 (错缝)
    if (offset > 0) {
      line.push($(go.Shape, 'Rectangle', {
        width: brickW / 2 - 1, height: brickH,
        fill: '#ECEFF1', stroke: '#B71C1C', strokeWidth: 1,
        margin: new go.Margin(0.5, 0.5),
      }))
    }
    const n = Math.ceil(rows * 2)
    for (let c = 0; c < n; c++) {
      line.push($(go.Shape, 'Rectangle', {
        width: brickW - 1, height: brickH,
        fill: '#ECEFF1', stroke: '#B71C1C', strokeWidth: 1,
        margin: new go.Margin(0.5, 0.5),
      }))
    }
    const p = $(go.Panel, 'Horizontal', line)
    if (offset > 0) p.margin = new go.Margin(0, 0, 0, -brickW / 2)
    wall.push(p)
  }
  return $(go.Panel, 'Vertical', wall)
}

// ---- Device Templates ----

// 路由器 (eNSP 风格): 圆形 + 上下两排对向箭头
function makeRouterTemplate() {
  const body = $(go.Shape, 'Ellipse', {
    fill: '#1565C0', stroke: '#0D47A1', strokeWidth: 2,
    minSize: new go.Size(74, 74),
    desiredSize: new go.Size(74, 74),
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(4, 6) },
        arrowGlyph(true),
        arrowGlyph(false),
      ),
    ),
    labelBlock(),
  )
}

// 交换机 (eNSP 风格): 矩形机架 + 双排对向箭头阵列
function makeSwitchTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#37474F', stroke: '#0D2B36', strokeWidth: 2,
    minSize: new go.Size(150, 54),
    parameter1: 4,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(5, 10) },
        arrowRow(-1, 5),
        arrowRow(1, 5),
      ),
    ),
    labelBlock(),
  )
}

function makePcTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#263238', stroke: '#000', strokeWidth: 2,
    width: 56, height: 42,
    parameter1: 3,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Shape, 'RoundedRectangle', {
        fill: '#1565C0', stroke: '#0D47A1',
        width: 48, height: 34,
        parameter1: 2,
        alignment: go.Spot.Center,
      }),
      $(go.Shape, 'Rectangle', {
        fill: '#37474F', stroke: '#263238',
        width: 8, height: 9,
        alignment: go.Spot.BottomCenter,
        alignmentFocus: go.Spot.TopCenter,
      }),
      $(go.Shape, 'Rectangle', {
        fill: '#37474F', stroke: '#263238',
        width: 28, height: 5,
        alignment: go.Spot.BottomCenter,
        alignmentFocus: go.Spot.TopCenter,
      }),
    ),
    labelBlock(),
  )
}

function makeLaptopTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#37474F', stroke: '#000', strokeWidth: 2,
    width: 50, height: 34,
    parameter1: 3,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Shape, 'RoundedRectangle', {
        fill: '#1565C0', stroke: '#0D47A1',
        width: 42, height: 26,
        parameter1: 2,
        alignment: go.Spot.Center,
      }),
      $(go.Shape, 'RoundedRectangle', {
        fill: '#37474F', stroke: '#263238',
        width: 60, height: 5,
        alignment: go.Spot.BottomCenter,
        alignmentFocus: go.Spot.TopCenter,
      }),
    ),
    labelBlock(),
  )
}

function makeServerTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#424242', stroke: '#212121', strokeWidth: 2,
    minSize: new go.Size(48, 68),
    parameter1: 3,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(6, 5, 5, 5) },
        $(go.Panel, 'Horizontal', { margin: new go.Margin(1, 0) },
          $(go.Shape, 'Rectangle', { width: 8, height: 3, fill: '#BDBDBD', stroke: null }),
          $(go.Shape, 'Rectangle', { width: 22, height: 7, fill: '#616161', stroke: '#424242', margin: new go.Margin(0, 2) }),
          $(go.Shape, 'Circle', { width: 3, height: 3, fill: '#4CAF50' }),
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(1, 0) },
          $(go.Shape, 'Rectangle', { width: 8, height: 3, fill: '#BDBDBD', stroke: null }),
          $(go.Shape, 'Rectangle', { width: 22, height: 7, fill: '#616161', stroke: '#424242', margin: new go.Margin(0, 2) }),
          $(go.Shape, 'Circle', { width: 3, height: 3, fill: '#4CAF50' }),
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(1, 0) },
          $(go.Shape, 'Rectangle', { width: 8, height: 3, fill: '#BDBDBD', stroke: null }),
          $(go.Shape, 'Rectangle', { width: 22, height: 7, fill: '#616161', stroke: '#424242', margin: new go.Margin(0, 2) }),
          $(go.Shape, 'Circle', { width: 3, height: 3, fill: '#FFC107' }),
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(3, 0, 0, 0) },
          $(go.Shape, 'Rectangle', { width: 14, height: 2, fill: '#616161', stroke: null, margin: 0.5 }),
          $(go.Shape, 'Rectangle', { width: 14, height: 2, fill: '#616161', stroke: null, margin: 0.5 }),
        ),
      ),
    ),
    labelBlock(),
  )
}

// 防火墙 (eNSP 风格): 砖墙图标
function makeFirewallTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#D84315', stroke: '#8D2A0B', strokeWidth: 2,
    minSize: new go.Size(104, 56),
    parameter1: 4,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(6, 10) },
        brickWall(3, 26, 8),
      ),
    ),
    labelBlock(),
  )
}

function makeApTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#ECEFF1', stroke: '#546E7A', strokeWidth: 2,
    width: 46, height: 32,
    parameter1: 8,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { alignment: go.Spot.Center },
        $(go.Shape, { geometryString: 'M 2 12 A 10 10 0 0 1 22 12', stroke: '#1565C0', strokeWidth: 2, fill: null, width: 24, height: 14 }),
        $(go.Shape, { geometryString: 'M 6 8 A 6 6 0 0 1 18 8', stroke: '#1565C0', strokeWidth: 2, fill: null, width: 24, height: 8 }),
        $(go.Shape, { geometryString: 'M 10 4 A 2 2 0 0 1 14 4', stroke: '#1565C0', strokeWidth: 2, fill: null, width: 24, height: 5 }),
      ),
    ),
    labelBlock(),
  )
}

function makeAcTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#7E57C2', stroke: '#4A148C', strokeWidth: 2,
    minSize: new go.Size(90, 50),
    parameter1: 4,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(4, 8) },
        $(go.Panel, 'Horizontal', { margin: new go.Margin(1, 0) },
          led('#4CAF50'), led('#4CAF50'), led('#4CAF50'), led('#FFC107')
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(3, 0, 0, 0) },
          $(go.Shape, 'Rectangle', { width: 55, height: 3, fill: '#4A148C', stroke: null }),
        ),
      ),
    ),
    labelBlock(),
  )
}

function makePhoneTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#37474F', stroke: '#000', strokeWidth: 2,
    width: 30, height: 44,
    parameter1: 4,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Shape, 'RoundedRectangle', {
        fill: '#E0E0E0', stroke: '#BDBDBD',
        width: 22, height: 32,
        parameter1: 2,
        alignment: go.Spot.Center,
        alignmentFocus: new go.Spot(0.5, 0.45),
      }),
      $(go.Shape, 'Circle', {
        width: 3, height: 3,
        fill: '#78909C',
        alignment: go.Spot.BottomCenter,
        alignmentFocus: go.Spot.TopCenter,
      }),
    ),
    labelBlock(),
  )
}

function makeCameraTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#ECEFF1', stroke: '#37474F', strokeWidth: 2,
    width: 48, height: 38,
    parameter1: 3,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Spot',
        $(go.Shape, { geometryString: 'M 4 16 Q 24 2 44 16', stroke: '#546E7A', strokeWidth: 2, fill: '#B0BEC5', width: 48, height: 20 }),
        $(go.Shape, 'Circle', { width: 10, height: 10, fill: '#263238', alignment: new go.Spot(0.5, 0.65) }),
        $(go.Shape, 'Circle', { width: 6, height: 6, fill: '#1565C0', alignment: new go.Spot(0.5, 0.65) }),
        $(go.Shape, 'Circle', { width: 3, height: 3, fill: '#42A5F5', alignment: new go.Spot(0.5, 0.65) }),
      ),
    ),
    labelBlock(),
  )
}

function makeNvrTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#37474F', stroke: '#212121', strokeWidth: 2,
    minSize: new go.Size(60, 50),
    parameter1: 3,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(5, 8) },
        $(go.Panel, 'Horizontal', { margin: new go.Margin(1, 0) },
          $(go.Shape, 'Rectangle', { width: 35, height: 5, fill: '#616161', stroke: null }),
          $(go.Shape, 'Circle', { width: 3, height: 3, fill: '#F44336', margin: new go.Margin(0, 0, 0, 3) }),
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(2, 0) },
          $(go.Shape, 'Rectangle', { width: 35, height: 5, fill: '#616161', stroke: null }),
          $(go.Shape, 'Circle', { width: 3, height: 3, fill: '#4CAF50', margin: new go.Margin(0, 0, 0, 3) }),
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(2, 0) },
          $(go.Shape, 'Rectangle', { width: 35, height: 5, fill: '#616161', stroke: null }),
          $(go.Shape, 'Circle', { width: 3, height: 3, fill: '#4CAF50', margin: new go.Margin(0, 0, 0, 3) }),
        ),
      ),
    ),
    labelBlock(),
  )
}

function makeDumbSwitchTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#546E7A', stroke: '#263238', strokeWidth: 2,
    minSize: new go.Size(116, 46),
    parameter1: 3,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(4, 8) },
        arrowRow(-1, 4),
        arrowRow(1, 4),
      ),
    ),
    labelBlock(),
  )
}

function makePrinterTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#ECEFF1', stroke: '#546E7A', strokeWidth: 2,
    minSize: new go.Size(64, 46),
    parameter1: 4,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(4, 6) },
        $(go.Shape, 'RoundedRectangle', { width: 46, height: 14, fill: '#B0BEC5', stroke: '#78909C', parameter1: 2 }),
        $(go.Shape, 'Rectangle', { width: 50, height: 4, fill: '#FAFAFA', stroke: '#BDBDBD', margin: new go.Margin(2, 0, 0, 0) }),
        $(go.Shape, 'RoundedRectangle', { width: 54, height: 5, fill: '#78909C', stroke: null, margin: new go.Margin(3, 0, 0, 0) }),
        $(go.Shape, 'Rectangle', { width: 30, height: 3, fill: '#546E7A', stroke: null, margin: new go.Margin(1, 0, 0, 18) }),
      ),
    ),
    labelBlock(),
  )
}

function makeIpsTemplate() {
  const body = $(go.Shape, 'RoundedRectangle', {
    fill: '#AB47BC', stroke: '#6A1B9A', strokeWidth: 2,
    minSize: new go.Size(110, 52),
    parameter1: 4,
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'BODY' },
      body,
      $(go.Panel, 'Vertical',
        { margin: new go.Margin(4, 8) },
        $(go.Panel, 'Horizontal', { margin: new go.Margin(1, 0) },
          $(go.Shape, 'Rectangle', { width: 70, height: 3, fill: '#6A1B9A', stroke: null }),
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(2, 0) },
          $(go.Shape, 'Rectangle', { width: 70, height: 3, fill: '#6A1B9A', stroke: null }),
        ),
        $(go.Panel, 'Horizontal', { margin: new go.Margin(4, 0, 0, 0) },
          led('#4CAF50'), led('#FFC107'), led('#4CAF50')
        ),
      ),
    ),
    labelBlock(),
  )
}

// 运营商/外网 (eNSP 风格): 云朵 (GoJS 核心无 Cloud figure, 用自定义几何)
const CLOUD_GEOMETRY = 'M 25 55 F M0 28 C0 15 10 8 21 10 C25 2 38 0 46 7 C52 2 64 3 69 10 C80 8 90 16 90 27 C98 30 98 44 88 48 C84 55 72 57 65 53 C58 58 40 58 34 53 C24 58 10 55 4 47 C0 43 0 34 2 30 Z'

function makeCloudTemplate() {
  const body = $(go.Shape, {
    geometryString: CLOUD_GEOMETRY,
    fill: '#E3F2FD', stroke: '#1565C0', strokeWidth: 2,
    minSize: new go.Size(92, 60),
  })
  linkableBody(body, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'BODY', selectionObjectName: 'BODY' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Spot',
      { name: 'BODY' },
      body,
    ),
    labelBlock(),
  )
}

// 安全域分区框: 虚线圆角矩形 + 区域名, 不可选中/移动/删除, 放在 Background 层
function makeZoneTemplate() {
  return $(go.Node, 'Spot',
    {
      selectable: false, movable: false, copyable: false, deletable: false,
      resizable: false, locationSpot: go.Spot.TopLeft,
    },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Spot',
      { name: 'BOX' },
      $(go.Shape, 'RoundedRectangle',
        {
          name: 'ZONE_BG',
          fill: 'rgba(236,242,248,0.42)', stroke: '#8FA3B5', strokeWidth: 1.5,
          strokeDashArray: [7, 4], parameter1: 10,
        },
        new go.Binding('desiredSize', 'size', go.Size.parse).makeTwoWay(go.Size.stringify)),
      $(go.TextBlock,
        {
          alignment: go.Spot.TopLeft, alignmentFocus: go.Spot.TopLeft,
          margin: new go.Margin(6, 12),
          font: 'bold 13px "Microsoft YaHei", sans-serif',
          stroke: '#607D8B',
        },
        new go.Binding('text', 'label')),
    ),
  )
}

// ---- Export template map and port specs ----

export function createNodeTemplateMap() {
  const map = new go.Map()
  // 实物图风格: NetEquip 图例库复刻
  map.add('router', makeRealIconTemplate(routerImg, 170, 42))
  map.add('switch', makeRealIconTemplate(switchImg, 180, 42))
  map.add('firewall', makeRealIconTemplate(firewallImg, 158, 46))
  map.add('ap', makeRealIconTemplate(apImg, 92, 48))
  map.add('server', makeRealIconTemplate(serverImg, 150, 36))
  // 矢量图标风格
  map.add('pc', makePcTemplate())
  map.add('laptop', makeLaptopTemplate())
  map.add('ips', makeIpsTemplate())
  map.add('camera', makeCameraTemplate())
  map.add('nvr', makeNvrTemplate())
  map.add('dumb-switch', makeDumbSwitchTemplate())
  map.add('printer', makePrinterTemplate())
  map.add('ac', makeAcTemplate())
  map.add('phone', makePhoneTemplate())
  map.add('cloud', makeCloudTemplate())
  // 专属实物图标: 负载均衡 / SDWAN / 上网行为管理 (AI 生成入库, 与 NetEquip 实物图同风格)
  map.add('lb', makeRealIconTemplate(lbImg, 92, 66))
  map.add('sdwan', makeRealIconTemplate(sdwanImg, 122, 58))
  map.add('behavior', makeRealIconTemplate(behaviorImg, 122, 60))
  map.add('zone', makeZoneTemplate())
  return map
}

// NetEquip 实物图模板: 白底 + 边框 + 图片 + 标签
function makeRealIconTemplate(src, w, h) {
  const pic = $(go.Picture, {
    source: src,
    desiredSize: new go.Size(w, h),
    imageStretch: go.GraphObject.Uniform,
  })
  linkableBody(pic, 'body')
  return $(go.Node, 'Spot',
    { locationObjectName: 'PIC', selectionObjectName: 'PIC' },
    new go.Binding('location', 'loc', go.Point.parse).makeTwoWay(go.Point.stringify),
    $(go.Panel, 'Auto',
      { name: 'PIC' },
      $(go.Shape, 'RoundedRectangle',
        { fill: '#FFFFFF', stroke: '#B0BEC5', strokeWidth: 1, parameter1: 3 }),
      pic,
    ),
    labelBlock(),
  )
}

export { PORT_SPECS }
