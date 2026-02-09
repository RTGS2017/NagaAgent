<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import { select as d3Select } from 'd3-selection'
import { drag } from 'd3-drag'
import { zoom } from 'd3-zoom'
import type { Simulation, SimulationNodeDatum, SimulationLinkDatum } from 'd3-force'
import API from '@/api/core'
import BoxContainer from '@/components/BoxContainer.vue'

interface Quintuple {
  subject: string
  subjectType: string
  predicate: string
  object: string
  objectType: string
}

interface GraphNode extends SimulationNodeDatum {
  id: string
  label: string
  type: string
}

interface GraphEdge extends SimulationLinkDatum<GraphNode> {
  label: string
}

const TYPE_COLORS: Record<string, string> = {
  '人物': '#FF6B6B',
  '地点': '#4ECDC4',
  '物品': '#45B7D1',
  '事件': '#96CEB4',
  '概念': '#FFEAA7',
  '组织': '#DDA0DD',
  '时间': '#87CEEB',
}
const DEFAULT_COLOR = '#A0A0A0'

function getColor(type: string) {
  return TYPE_COLORS[type] || DEFAULT_COLOR
}

const svgRef = ref<SVGSVGElement>()
const quintuples = ref<Quintuple[]>([])
const loading = ref(true)
const error = ref('')
const searchQuery = ref('')
const nodeCount = ref(0)

let simulation: Simulation<GraphNode, GraphEdge> | null = null

function buildGraphData(quints: Quintuple[]) {
  const nodeMap = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []
  for (const q of quints) {
    if (!nodeMap.has(q.subject)) {
      nodeMap.set(q.subject, { id: q.subject, label: q.subject, type: q.subjectType })
    }
    if (!nodeMap.has(q.object)) {
      nodeMap.set(q.object, { id: q.object, label: q.object, type: q.objectType })
    }
    edges.push({ source: q.subject, target: q.object, label: q.predicate })
  }
  const nodes = [...nodeMap.values()]
  nodeCount.value = nodes.length
  return { nodes, edges }
}

function renderGraph(quints: Quintuple[]) {
  if (!svgRef.value || quints.length === 0) return

  // Clean up previous
  if (simulation) {
    simulation.stop()
    simulation = null
  }
  d3Select(svgRef.value).selectAll('*').remove()

  const container = svgRef.value.parentElement
  if (!container) return
  const width = container.clientWidth
  const height = container.clientHeight

  const svg = d3Select(svgRef.value)
    .attr('width', width)
    .attr('height', height)

  // Zoom support
  const g = svg.append('g')
  svg.call(
    zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      }) as any,
  )

  const { nodes, edges } = buildGraphData(quints)

  simulation = forceSimulation<GraphNode>(nodes)
    .force('link', forceLink<GraphNode, GraphEdge>(edges).id(d => d.id).distance(100))
    .force('charge', forceManyBody().strength(-300))
    .force('center', forceCenter(width / 2, height / 2))
    .force('collide', forceCollide().radius(35))

  // Edges
  const link = g.append('g')
    .selectAll('line')
    .data(edges)
    .join('line')
    .attr('stroke', '#999')
    .attr('stroke-opacity', 0.6)
    .attr('stroke-width', 2)

  // Edge labels
  const edgeLabel = g.append('g')
    .selectAll('text')
    .data(edges)
    .join('text')
    .text(d => d.label)
    .attr('font-size', '10px')
    .attr('fill', '#888')
    .attr('text-anchor', 'middle')

  // Nodes
  const node = g.append('g')
    .selectAll('circle')
    .data(nodes)
    .join('circle')
    .attr('r', 20)
    .attr('fill', d => getColor(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)
    .attr('cursor', 'pointer')
    .call(
      drag<SVGCircleElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) simulation?.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (event, d) => {
          d.fx = event.x
          d.fy = event.y
        })
        .on('end', (event, d) => {
          if (!event.active) simulation?.alphaTarget(0)
          d.fx = null
          d.fy = null
        }),
    )

  // Node labels
  const label = g.append('g')
    .selectAll('text')
    .data(nodes)
    .join('text')
    .text(d => d.label)
    .attr('font-size', '12px')
    .attr('fill', '#fff')
    .attr('text-anchor', 'middle')
    .attr('dy', -25)
    .attr('pointer-events', 'none')

  simulation.on('tick', () => {
    link
      .attr('x1', d => (d.source as GraphNode).x!)
      .attr('y1', d => (d.source as GraphNode).y!)
      .attr('x2', d => (d.target as GraphNode).x!)
      .attr('y2', d => (d.target as GraphNode).y!)

    edgeLabel
      .attr('x', d => ((d.source as GraphNode).x! + (d.target as GraphNode).x!) / 2)
      .attr('y', d => ((d.source as GraphNode).y! + (d.target as GraphNode).y!) / 2)

    node
      .attr('cx', d => d.x!)
      .attr('cy', d => d.y!)

    label
      .attr('x', d => d.x!)
      .attr('y', d => d.y!)
  })
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const res = await API.getQuintuples()
    quintuples.value = res.quintuples ?? []
  } catch (e: any) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function search() {
  if (!searchQuery.value.trim()) {
    await loadData()
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await API.searchQuintuples(searchQuery.value)
    quintuples.value = res.quintuples ?? []
  } catch (e: any) {
    error.value = e.message || '搜索失败'
  } finally {
    loading.value = false
  }
}

watch(quintuples, (q) => {
  renderGraph(q)
})

onMounted(async () => {
  await loadData()
})

onUnmounted(() => {
  if (simulation) {
    simulation.stop()
    simulation = null
  }
})
</script>

<template>
  <BoxContainer class="w-full h-full flex flex-col">
    <div class="text-white flex flex-col h-full">
      <!-- Header -->
      <div class="flex items-center gap-3 mb-3 shrink-0">
        <h2 class="text-lg font-bold">
          记忆云海
        </h2>
        <div class="flex-1 flex items-center gap-2">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索关键词..."
            class="flex-1 bg-white/10 border border-white/20 rounded px-3 py-1.5 text-sm text-white placeholder-white/40 outline-none focus:border-white/40"
            @keyup.enter="search"
          >
          <button
            class="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition"
            @click="search"
          >
            搜索
          </button>
          <button
            class="px-3 py-1.5 bg-white/10 hover:bg-white/20 rounded text-sm transition"
            @click="searchQuery = ''; loadData()"
          >
            刷新
          </button>
        </div>
      </div>

      <!-- Stats -->
      <div class="flex gap-4 text-xs text-white/50 mb-2 shrink-0">
        <span>五元组: {{ quintuples.length }}</span>
        <span>实体: {{ nodeCount }}</span>
      </div>

      <!-- Graph -->
      <div class="flex-1 relative min-h-0 rounded-lg overflow-hidden bg-[rgba(30,30,30,0.8)] border border-white/10">
        <div v-if="loading" class="absolute inset-0 flex items-center justify-center bg-black/40 z-10">
          <span class="text-white/60">加载中...</span>
        </div>
        <div v-else-if="error" class="absolute inset-0 flex items-center justify-center">
          <span class="text-red-400">{{ error }}</span>
        </div>
        <div
          v-else-if="quintuples.length === 0"
          class="absolute inset-0 flex flex-col items-center justify-center text-white/40"
        >
          <p>暂无五元组数据</p>
          <p class="text-xs mt-1">
            请先进行对话以生成知识图谱，或前往「记忆链接」启用 GRAG
          </p>
        </div>
        <svg ref="svgRef" class="w-full h-full" />
      </div>

      <!-- Legend -->
      <div class="flex flex-wrap gap-3 mt-2 shrink-0">
        <div v-for="(color, type) in TYPE_COLORS" :key="type" class="flex items-center gap-1 text-xs text-white/60">
          <span class="inline-block w-3 h-3 rounded-full" :style="{ background: color }" />
          {{ type }}
        </div>
      </div>
    </div>
  </BoxContainer>
</template>
