package service

import (
	"context"
	"testing"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestProjectService_Create(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	project, err := svc.Create(ctx, CreateProjectInput{
		Name:        "my-project",
		Description: "A test project",
	})

	require.NoError(t, err)
	assert.Equal(t, "my-project", project.Name)
	assert.Equal(t, "A test project", project.Description)
	assert.NotEqual(t, uuid.Nil, project.ID)
}

func TestProjectService_Create_ValidationError(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	_, err := svc.Create(ctx, CreateProjectInput{
		Name: "",
	})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "name is required")
}

func TestProjectService_Get(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	created, err := svc.Create(ctx, CreateProjectInput{
		Name:        "my-project",
		Description: "A test project",
	})
	require.NoError(t, err)

	project, err := svc.Get(ctx, created.ID)
	require.NoError(t, err)
	assert.Equal(t, created.ID, project.ID)
	assert.Equal(t, "my-project", project.Name)
}

func TestProjectService_List(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	_, err := svc.Create(ctx, CreateProjectInput{Name: "project-1"})
	require.NoError(t, err)
	_, err = svc.Create(ctx, CreateProjectInput{Name: "project-2"})
	require.NoError(t, err)

	projects, err := svc.List(ctx)
	require.NoError(t, err)
	assert.Len(t, projects, 2)
}

func TestProjectService_Update(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	created, err := svc.Create(ctx, CreateProjectInput{
		Name:        "my-project",
		Description: "Original",
	})
	require.NoError(t, err)

	newName := "renamed-project"
	newDesc := "Updated description"
	updated, err := svc.Update(ctx, created.ID, UpdateProjectInput{
		Name:        &newName,
		Description: &newDesc,
	})
	require.NoError(t, err)
	assert.Equal(t, created.ID, updated.ID)
	assert.Equal(t, "renamed-project", updated.Name)
	assert.Equal(t, "Updated description", updated.Description)
}

func TestProjectService_Update_PartialName(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	created, err := svc.Create(ctx, CreateProjectInput{
		Name:        "my-project",
		Description: "Original",
	})
	require.NoError(t, err)

	// Only update description, name stays the same.
	newDesc := "New description"
	updated, err := svc.Update(ctx, created.ID, UpdateProjectInput{
		Description: &newDesc,
	})
	require.NoError(t, err)
	assert.Equal(t, "my-project", updated.Name)
	assert.Equal(t, "New description", updated.Description)
}

func TestProjectService_Update_EmptyName(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	created, err := svc.Create(ctx, CreateProjectInput{
		Name: "my-project",
	})
	require.NoError(t, err)

	emptyName := ""
	_, err = svc.Update(ctx, created.ID, UpdateProjectInput{Name: &emptyName})
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "name is required")
}

func TestProjectService_Delete(t *testing.T) {
	mq := newMockQuerier()
	svc := NewProjectService(mq, testLogger())
	ctx := context.Background()

	created, err := svc.Create(ctx, CreateProjectInput{Name: "to-delete"})
	require.NoError(t, err)

	err = svc.Delete(ctx, created.ID)
	require.NoError(t, err)

	// Subsequent get should fail.
	_, err = svc.Get(ctx, created.ID)
	assert.Error(t, err)
}
