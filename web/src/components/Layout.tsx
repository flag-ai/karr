import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard' },
  { to: '/agents', label: 'Agents' },
  { to: '/projects', label: 'Projects' },
  { to: '/environments', label: 'Environments' },
]

export default function Layout() {
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <nav style={{
        width: 220,
        backgroundColor: 'var(--mantle)',
        padding: '20px 0',
        borderRight: '1px solid var(--surface0)',
        flexShrink: 0,
      }}>
        <div style={{
          padding: '0 20px 20px',
          fontSize: 20,
          fontWeight: 700,
          color: 'var(--blue)',
          letterSpacing: 2,
        }}>
          KARR
        </div>
        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            style={({ isActive }) => ({
              display: 'block',
              padding: '10px 20px',
              color: isActive ? 'var(--blue)' : 'var(--subtext1)',
              backgroundColor: isActive ? 'var(--surface0)' : 'transparent',
              borderLeft: isActive ? '3px solid var(--blue)' : '3px solid transparent',
              fontSize: 14,
              fontWeight: isActive ? 600 : 400,
              transition: 'all 0.15s',
            })}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main style={{
        flex: 1,
        padding: 24,
        backgroundColor: 'var(--base)',
        overflow: 'auto',
      }}>
        <Outlet />
      </main>
    </div>
  )
}
