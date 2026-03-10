package bonnie

import "time"

// GPUVendor identifies the GPU manufacturer.
type GPUVendor string

const (
	GPUVendorNVIDIA  GPUVendor = "nvidia"
	GPUVendorAMD     GPUVendor = "amd"
	GPUVendorIntel   GPUVendor = "intel"
	GPUVendorUnknown GPUVendor = "none"
)

// GPUInfo describes a single GPU on a BONNIE host.
type GPUInfo struct {
	Index       int       `json:"index"`
	Name        string    `json:"name"`
	Vendor      GPUVendor `json:"vendor"`
	MemoryTotal uint64    `json:"memory_total_mib"`
	MemoryFree  uint64    `json:"memory_free_mib"`
	Utilization int       `json:"utilization_percent"`
}

// GPUSnapshot is a point-in-time view of all GPUs on a host.
type GPUSnapshot struct {
	Vendor    GPUVendor `json:"vendor"`
	GPUs      []GPUInfo `json:"gpus"`
	Timestamp time.Time `json:"timestamp"`
}

// SystemInfo describes the host system.
type SystemInfo struct {
	Hostname string `json:"hostname"`
	OS       string `json:"os"`
	Arch     string `json:"arch"`
	Kernel   string `json:"kernel"`
	CPUModel string `json:"cpu_model"`
	CPUCores int    `json:"cpu_cores"`
	MemoryMB uint64 `json:"memory_mb"`
}

// DiskUsage reports disk usage.
type DiskUsage struct {
	TotalGB     float64 `json:"total_gb"`
	UsedGB      float64 `json:"used_gb"`
	AvailableGB float64 `json:"available_gb"`
	UsedPercent string  `json:"used_percent"`
}

// SystemInfoResponse combines system info and disk usage.
type SystemInfoResponse struct {
	System SystemInfo `json:"system"`
	Disk   DiskUsage  `json:"disk"`
}

// ContainerInfo is a summary of a container's state.
type ContainerInfo struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Image   string `json:"image"`
	State   string `json:"state"`
	Status  string `json:"status"`
	Created int64  `json:"created"`
}

// CreateContainerRequest describes a container to create on a BONNIE host.
type CreateContainerRequest struct {
	Name    string   `json:"name"`
	Image   string   `json:"image"`
	Env     []string `json:"env,omitempty"`
	Mounts  []string `json:"mounts,omitempty"`
	GPU     bool     `json:"gpu"`
	Command []string `json:"command,omitempty"`
}
