import { createRouter, createWebHistory } from 'vue-router'
import KbList from '../components/KbList.vue'
import KbDetail from '../components/KbDetail.vue'
import QueryView from '../components/QueryView.vue'
import VectorDataView from '../components/VectorDataView.vue'

const routes = [
  { path: '/', name: 'kb', component: KbList },
  { path: '/kb/:kbId', name: 'kb-detail', component: KbDetail, props: true },
  { path: '/query', name: 'query', component: QueryView },
  { path: '/vectors', name: 'vectors', component: VectorDataView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
