function DashboardCard({ title, value, detail, color }) {
  return (
    <article className={`dashboard-card ${color}`}>
      <div className="card-topline">
        <span className="status-dot"></span>
        <span>Live</span>
      </div>

      <h3>{title}</h3>
      <strong>{value}</strong>
      <p>{detail}</p>
    </article>
  )
}

export default DashboardCard