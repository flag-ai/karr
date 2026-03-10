package environment

import (
	"fmt"
	"io"

	"gopkg.in/yaml.v3"
)

// ParseSpec reads a YAML spec from the given reader and validates it.
func ParseSpec(r io.Reader) (*Spec, error) {
	var spec Spec
	dec := yaml.NewDecoder(r)
	dec.KnownFields(true) // reject unknown fields
	if err := dec.Decode(&spec); err != nil {
		return nil, fmt.Errorf("parse spec: %w", err)
	}

	if err := validateSpec(&spec); err != nil {
		return nil, err
	}

	return &spec, nil
}

func validateSpec(spec *Spec) error {
	if spec.Name == "" {
		return fmt.Errorf("spec: name is required")
	}
	if spec.Agent == "" {
		return fmt.Errorf("spec: agent is required")
	}
	if spec.Image == "" {
		return fmt.Errorf("spec: image is required")
	}
	return nil
}
