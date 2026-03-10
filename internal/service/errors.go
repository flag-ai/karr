package service

import "errors"

// ErrNotFound is returned when a requested resource does not exist.
var ErrNotFound = errors.New("not found")
