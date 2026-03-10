package environment

// Spec describes an environment to be created from a YAML file.
type Spec struct {
	Name    string   `yaml:"name"`
	Agent   string   `yaml:"agent"`
	Project string   `yaml:"project,omitempty"`
	Image   string   `yaml:"image"`
	GPU     bool     `yaml:"gpu,omitempty"`
	Env     []string `yaml:"env,omitempty"`
	Mounts  []string `yaml:"mounts,omitempty"`
	Command []string `yaml:"command,omitempty"`
}
