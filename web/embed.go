// Package web provides the embedded SPA frontend assets.
package web

import "embed"

// Dist contains the built React SPA files from web/dist/.
//
//go:embed all:dist
var Dist embed.FS
