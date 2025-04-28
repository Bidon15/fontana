"""
Tests for the Sparse Merkle Tree implementation.
"""
import pytest
from fontana.core.state_merkle import SparseMerkleTree


def test_smt_empty_tree():
    """Test that a new empty tree has the expected root."""
    tree = SparseMerkleTree()
    assert tree.get_root() == tree.EMPTY_NODE_HASH


def test_smt_add_single_leaf():
    """Test adding a single leaf to the tree."""
    tree = SparseMerkleTree()
    initial_root = tree.get_root()
    
    # Add a leaf
    tree.update("test-key", "test-value")
    
    # Check root has changed
    assert tree.get_root() != initial_root
    
    # Check key exists
    assert tree.get("test-key") is not None


def test_smt_add_multiple_leaves():
    """Test adding multiple leaves to the tree."""
    tree = SparseMerkleTree()
    
    # Add several leaves
    tree.update("key1", "value1")
    first_root = tree.get_root()
    
    tree.update("key2", "value2")
    assert tree.get_root() != first_root
    
    tree.update("key3", "value3")
    
    # Check all keys exist
    assert "key1" in tree.get_all_keys()
    assert "key2" in tree.get_all_keys()
    assert "key3" in tree.get_all_keys()
    assert len(tree.get_all_keys()) == 3


def test_smt_update_leaf():
    """Test updating an existing leaf."""
    tree = SparseMerkleTree()
    
    # Add a leaf
    tree.update("key1", "value1")
    initial_root = tree.get_root()
    
    # Update the leaf
    tree.update("key1", "updated-value")
    
    # Check root has changed
    assert tree.get_root() != initial_root
    
    # Check key still exists
    assert "key1" in tree.get_all_keys()
    assert len(tree.get_all_keys()) == 1


def test_smt_delete_leaf():
    """Test deleting a leaf."""
    tree = SparseMerkleTree()
    
    # Add leaves
    tree.update("key1", "value1")
    tree.update("key2", "value2")
    
    # Check keys exist
    assert "key1" in tree.get_all_keys()
    assert "key2" in tree.get_all_keys()
    assert len(tree.get_all_keys()) == 2
    
    # Delete a leaf
    tree.update("key1", None)
    
    # Check key was deleted
    assert "key1" not in tree.get_all_keys()
    assert "key2" in tree.get_all_keys()
    assert len(tree.get_all_keys()) == 1


def test_smt_generate_verify_proof():
    """Test generating and verifying a proof."""
    tree = SparseMerkleTree()
    
    # Add some leaves
    tree.update("key1", "value1")
    tree.update("key2", "value2")
    tree.update("key3", "value3")
    
    # Save the root
    root = tree.get_root()
    
    # Generate a proof
    proof = tree.generate_proof("key2")
    
    # Verify the proof
    assert proof is not None
    assert tree.verify_proof("key2", "value2", proof, root)
    
    # Verify the proof fails for wrong key/value
    assert not tree.verify_proof("key2", "wrong-value", proof, root)
    assert not tree.verify_proof("wrong-key", "value2", proof, root)
    
    # Verify against a different root
    tree.update("key4", "value4")
    new_root = tree.get_root()
    assert new_root != root
    assert not tree.verify_proof("key2", "value2", proof, new_root)


def test_smt_proof_for_nonexistent_key():
    """Test generating a proof for a nonexistent key."""
    tree = SparseMerkleTree()
    
    # Add a leaf
    tree.update("key1", "value1")
    
    # Generate a proof for a nonexistent key
    proof = tree.generate_proof("nonexistent-key")
    
    # Should return None
    assert proof is None


def test_smt_consistency():
    """Test that the tree maintains consistent state through operations."""
    tree = SparseMerkleTree()
    
    # Perform a series of operations
    tree.update("key1", "value1")
    root1 = tree.get_root()
    
    tree.update("key2", "value2")
    root2 = tree.get_root()
    
    tree.update("key1", None)  # Delete key1
    root3 = tree.get_root()
    
    tree.update("key1", "value1-new")  # Add key1 again
    root4 = tree.get_root()
    
    # Verify all roots are different
    assert root1 != root2 != root3 != root4
    
    # Check final state
    assert "key1" in tree.get_all_keys()
    assert "key2" in tree.get_all_keys()
    assert len(tree.get_all_keys()) == 2
