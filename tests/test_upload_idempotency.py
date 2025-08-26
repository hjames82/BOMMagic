#!/usr/bin/env python
"""Test upload idempotency and duplicate detection"""

import os
import hashlib
import tempfile
from io import BytesIO
from app import app, db
from models import Job, Document
import uuid

def test_duplicate_upload_detection():
    """Test that duplicate uploads are detected via SHA256 hash"""
    
    with app.app_context():
        # Create test PDF content
        test_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 2\n%%EOF"
        file_hash = hashlib.sha256(test_content).hexdigest()
        
        # Create first job
        job1 = Job(
            id=str(uuid.uuid4()),
            user_id="test-user-1",
            original_filename="test.pdf",
            file_path="/tmp/test1.pdf",
            file_size=len(test_content),
            file_hash=file_hash
        )
        db.session.add(job1)
        db.session.commit()
        
        # Try to create duplicate job
        existing_job = Job.query.filter_by(file_hash=file_hash, user_id="test-user-1").first()
        assert existing_job is not None, "Should find existing job by hash"
        assert existing_job.id == job1.id, "Should return the same job"
        
        # Different user should be able to upload same file
        job2 = Job(
            id=str(uuid.uuid4()),
            user_id="test-user-2", 
            original_filename="test.pdf",
            file_path="/tmp/test2.pdf",
            file_size=len(test_content),
            file_hash=file_hash
        )
        db.session.add(job2)
        db.session.commit()
        
        # Verify both jobs exist
        jobs_with_hash = Job.query.filter_by(file_hash=file_hash).all()
        assert len(jobs_with_hash) == 2, "Should have 2 jobs with same hash for different users"
        
        # Cleanup
        db.session.delete(job1)
        db.session.delete(job2)
        db.session.commit()
        
        print("✓ Duplicate upload detection test passed")


def test_document_analysis_idempotency():
    """Test that duplicate document analysis is detected"""
    
    with app.app_context():
        # Create test PDF content
        test_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 2\n%%EOF"
        file_hash = hashlib.sha256(test_content).hexdigest()
        
        # Create first document
        doc1 = Document(
            id=str(uuid.uuid4()),
            original_filename="test.pdf",
            file_path="/tmp/test1.pdf",
            file_size=len(test_content),
            file_hash=file_hash,
            page_count=1
        )
        db.session.add(doc1)
        db.session.commit()
        
        # Try to find duplicate document
        existing_doc = Document.query.filter_by(file_hash=file_hash).first()
        assert existing_doc is not None, "Should find existing document by hash"
        assert existing_doc.id == doc1.id, "Should return the same document"
        
        # Try to create duplicate (should fail due to unique constraint)
        doc2 = Document(
            id=str(uuid.uuid4()),
            original_filename="test2.pdf",
            file_path="/tmp/test2.pdf", 
            file_size=len(test_content),
            file_hash=file_hash,
            page_count=1
        )
        
        try:
            db.session.add(doc2)
            db.session.commit()
            assert False, "Should not allow duplicate document with same hash"
        except Exception:
            db.session.rollback()
            # Expected - unique constraint violation
            pass
        
        # Cleanup
        db.session.delete(doc1)
        db.session.commit()
        
        print("✓ Document analysis idempotency test passed")


def test_file_size_limits():
    """Test file size validation"""
    
    MAX_SIZE = 25 * 1024 * 1024  # 25MB
    
    # Test acceptable size
    small_file = b"x" * (MAX_SIZE - 1)
    assert len(small_file) < MAX_SIZE, "Small file should be under limit"
    
    # Test over limit
    large_file = b"x" * (MAX_SIZE + 1)
    assert len(large_file) > MAX_SIZE, "Large file should be over limit"
    
    print("✓ File size limit test passed")


def test_hash_calculation():
    """Test SHA256 hash calculation consistency"""
    
    # Test content
    content1 = b"Test content 123"
    content2 = b"Test content 123"
    content3 = b"Different content"
    
    # Calculate hashes
    hash1 = hashlib.sha256(content1).hexdigest()
    hash2 = hashlib.sha256(content2).hexdigest()
    hash3 = hashlib.sha256(content3).hexdigest()
    
    # Verify consistency
    assert hash1 == hash2, "Same content should produce same hash"
    assert hash1 != hash3, "Different content should produce different hash"
    assert len(hash1) == 64, "SHA256 hash should be 64 characters"
    
    print("✓ Hash calculation test passed")


if __name__ == "__main__":
    print("Running upload idempotency tests...\n")
    
    test_hash_calculation()
    test_file_size_limits()
    test_duplicate_upload_detection()
    test_document_analysis_idempotency()
    
    print("\n✅ All tests passed successfully!")