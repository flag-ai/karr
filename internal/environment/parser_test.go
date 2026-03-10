package environment

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseSpec_AllFields(t *testing.T) {
	input := `
name: my-env
agent: gpu-agent-1
project: my-project
image: nvidia/cuda:12.0
gpu: true
env:
  - CUDA_VISIBLE_DEVICES=0
  - DEBUG=1
mounts:
  - /data:/data
command:
  - python
  - train.py
`
	spec, err := ParseSpec(strings.NewReader(input))
	require.NoError(t, err)

	assert.Equal(t, "my-env", spec.Name)
	assert.Equal(t, "gpu-agent-1", spec.Agent)
	assert.Equal(t, "my-project", spec.Project)
	assert.Equal(t, "nvidia/cuda:12.0", spec.Image)
	assert.True(t, spec.GPU)
	assert.Equal(t, []string{"CUDA_VISIBLE_DEVICES=0", "DEBUG=1"}, spec.Env)
	assert.Equal(t, []string{"/data:/data"}, spec.Mounts)
	assert.Equal(t, []string{"python", "train.py"}, spec.Command)
}

func TestParseSpec_RequiredFieldsOnly(t *testing.T) {
	input := `
name: minimal-env
agent: agent-1
image: ubuntu:22.04
`
	spec, err := ParseSpec(strings.NewReader(input))
	require.NoError(t, err)

	assert.Equal(t, "minimal-env", spec.Name)
	assert.Equal(t, "agent-1", spec.Agent)
	assert.Equal(t, "ubuntu:22.04", spec.Image)
	assert.Empty(t, spec.Project)
	assert.False(t, spec.GPU)
	assert.Nil(t, spec.Env)
	assert.Nil(t, spec.Mounts)
	assert.Nil(t, spec.Command)
}

func TestParseSpec_MissingName(t *testing.T) {
	input := `
agent: agent-1
image: ubuntu:22.04
`
	_, err := ParseSpec(strings.NewReader(input))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "name is required")
}

func TestParseSpec_MissingAgent(t *testing.T) {
	input := `
name: my-env
image: ubuntu:22.04
`
	_, err := ParseSpec(strings.NewReader(input))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "agent is required")
}

func TestParseSpec_MissingImage(t *testing.T) {
	input := `
name: my-env
agent: agent-1
`
	_, err := ParseSpec(strings.NewReader(input))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "image is required")
}

func TestParseSpec_InvalidYAML(t *testing.T) {
	input := `
name: my-env
  bad-indent: oops
`
	_, err := ParseSpec(strings.NewReader(input))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "parse spec")
}

func TestParseSpec_UnknownField(t *testing.T) {
	input := `
name: my-env
agent: agent-1
image: ubuntu:22.04
unknown_field: something
`
	_, err := ParseSpec(strings.NewReader(input))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "parse spec")
}
