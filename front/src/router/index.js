import { createRouter, createWebHistory } from 'vue-router'
import KbList from '../components/KbList.vue'
import KbDetail from '../components/KbDetail.vue'
import QueryView from '../components/QueryView.vue'
import VectorDataView from '../components/VectorDataView.vue'
import GraphView from '../components/GraphView.vue'

const routes = [
  { path: '/', name: 'kb', component: KbList, meta: { keepAlive: true } },
  { path: '/kb/:kbId', name: 'kb-detail', component: KbDetail, props: true },
  { path: '/query', name: 'query', component: QueryView, meta: { keepAlive: true } },
  { path: '/vectors', name: 'vectors', component: VectorDataView, meta: { keepAlive: true } },
  { path: '/graph', name: 'graph', component: GraphView, meta: { keepAlive: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
