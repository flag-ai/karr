import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Agents from './pages/Agents'
import Projects from './pages/Projects'
import Environments from './pages/Environments'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/environments" element={<Environments />} />
      </Route>
    </Routes>
  )
}
