#!/usr/bin/env python3
"""
BOM Detection Evaluation Tool
Evaluates detection accuracy against golden dataset
"""

import os
import sys
import json
import yaml
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """Calculate Intersection over Union between two bounding boxes."""
    # box format: [x0, y0, x1, y1]
    x0 = max(box1[0], box2[0])
    y0 = max(box1[1], box2[1])
    x1 = min(box1[2], box2[2])
    y1 = min(box1[3], box2[3])
    
    if x0 >= x1 or y0 >= y1:
        return 0.0
    
    intersection = (x1 - x0) * (y1 - y0)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0


def evaluate_detection(detection: Dict, ground_truth: Dict, iou_threshold: float = 0.6) -> Dict:
    """Evaluate a single detection against ground truth."""
    result = {
        'filename': ground_truth['filename'],
        'category': ground_truth['category'],
        'detected': False,
        'correct': False,
        'iou': 0.0,
        'confidence': 0.0,
        'false_positive': False,
        'page_match': False,
        'headers_match': False
    }
    
    # Check if this is a negative case (no BOM expected)
    if ground_truth['category'] == 'no_bom':
        if detection and len(detection.get('detections', [])) > 0:
            result['false_positive'] = True
            result['detected'] = True
            result['confidence'] = detection['detections'][0].get('confidence', 0)
        else:
            result['correct'] = True
        return result
    
    # For positive cases, check detection
    if not detection or len(detection.get('detections', [])) == 0:
        return result  # False negative
    
    result['detected'] = True
    top_detection = detection['detections'][0]  # Use highest confidence
    result['confidence'] = top_detection.get('confidence', 0)
    
    # Check page match
    if top_detection['page'] == ground_truth['expected_page']:
        result['page_match'] = True
    
    # Check bbox IoU
    if ground_truth.get('bbox'):
        pred_bbox = top_detection['bbox']
        gt_bbox = ground_truth['bbox']
        iou = calculate_iou(pred_bbox, gt_bbox)
        result['iou'] = iou
        
        if iou >= iou_threshold:
            result['correct'] = True
    
    # Check header match
    detected_headers = set(h.lower() for h in top_detection.get('headers', []))
    expected_headers = set(h.lower() for h in ground_truth.get('headers', []))
    if expected_headers:
        overlap = detected_headers.intersection(expected_headers)
        result['headers_match'] = len(overlap) >= len(expected_headers) * 0.5
    
    return result


def run_evaluation(api_url: str, manifest_path: str, pdf_dir: str) -> Dict:
    """Run evaluation on entire golden dataset."""
    # Load manifest
    with open(manifest_path, 'r') as f:
        manifest = yaml.safe_load(f)
    
    results = []
    timings = []
    
    print(f"Running evaluation on {len(manifest['files'])} files...")
    print("-" * 60)
    
    for file_info in manifest['files']:
        filename = file_info['filename']
        pdf_path = os.path.join(pdf_dir, filename)
        
        # Skip if file doesn't exist
        if not os.path.exists(pdf_path):
            print(f"⚠️  Skipping {filename} - file not found")
            continue
        
        print(f"Testing: {filename} ({file_info['category']})")
        
        # Call API
        start_time = time.time()
        try:
            with open(pdf_path, 'rb') as f:
                files = {'file': (filename, f, 'application/pdf')}
                response = requests.post(api_url, files=files, timeout=60)
            
            if response.status_code == 201:
                detection_result = response.json()
            else:
                print(f"  ❌ API error: {response.status_code}")
                detection_result = None
        except Exception as e:
            print(f"  ❌ Request failed: {str(e)}")
            detection_result = None
        
        elapsed = time.time() - start_time
        timings.append(elapsed)
        
        # Evaluate
        eval_result = evaluate_detection(detection_result, file_info)
        results.append(eval_result)
        
        # Print result
        if eval_result['category'] == 'no_bom':
            if eval_result['correct']:
                print(f"  ✅ Correctly identified as non-BOM")
            else:
                print(f"  ❌ False positive (confidence: {eval_result['confidence']:.2f})")
        else:
            if eval_result['correct']:
                print(f"  ✅ Correct detection (IoU: {eval_result['iou']:.2f}, confidence: {eval_result['confidence']:.2f})")
            elif eval_result['detected']:
                print(f"  ⚠️  Detected but incorrect (IoU: {eval_result['iou']:.2f}, page: {eval_result['page_match']})")
            else:
                print(f"  ❌ Missed detection")
    
    print("-" * 60)
    
    # Calculate metrics
    metrics = calculate_metrics(results, manifest['evaluation'])
    
    return {
        'results': results,
        'metrics': metrics,
        'timings': timings,
        'timestamp': datetime.now().isoformat()
    }


def calculate_metrics(results: List[Dict], eval_config: Dict) -> Dict:
    """Calculate precision, recall, F1 score."""
    # Separate by category
    positive_results = [r for r in results if r['category'] != 'no_bom']
    negative_results = [r for r in results if r['category'] == 'no_bom']
    
    # Positive cases
    true_positives = sum(1 for r in positive_results if r['correct'])
    false_negatives = sum(1 for r in positive_results if not r['detected'])
    false_positives_partial = sum(1 for r in positive_results if r['detected'] and not r['correct'])
    
    # Negative cases
    true_negatives = sum(1 for r in negative_results if r['correct'])
    false_positives_negative = sum(1 for r in negative_results if r['false_positive'])
    
    # Calculate metrics
    precision = true_positives / (true_positives + false_positives_partial + false_positives_negative) if (true_positives + false_positives_partial + false_positives_negative) > 0 else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    # Average confidence
    confidences = [r['confidence'] for r in results if r['detected']]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    
    # Check gates
    passed_f1_gate = f1_score >= eval_config.get('target_f1_score', 0.90)
    passed_fp_gate = false_positives_negative <= eval_config.get('max_false_positives_on_negatives', 1)
    
    return {
        'true_positives': true_positives,
        'false_negatives': false_negatives,
        'false_positives_partial': false_positives_partial,
        'true_negatives': true_negatives,
        'false_positives_negative': false_positives_negative,
        'precision': precision,
        'recall': recall,
        'f1_score': f1_score,
        'average_confidence': avg_confidence,
        'passed_f1_gate': passed_f1_gate,
        'passed_fp_gate': passed_fp_gate,
        'all_gates_passed': passed_f1_gate and passed_fp_gate
    }


def write_reports(evaluation: Dict, output_dir: str):
    """Write JSON and Markdown reports."""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Write JSON report
    json_path = os.path.join(output_dir, f"eval_{timestamp}.json")
    with open(json_path, 'w') as f:
        json.dump(evaluation, f, indent=2)
    
    # Write Markdown report
    md_path = os.path.join(output_dir, f"eval_{timestamp}.md")
    metrics = evaluation['metrics']
    
    with open(md_path, 'w') as f:
        f.write("# BOM Detection Evaluation Report\n\n")
        f.write(f"**Date:** {evaluation['timestamp']}\n\n")
        
        f.write("## Summary Metrics\n\n")
        f.write(f"- **Precision:** {metrics['precision']:.2%}\n")
        f.write(f"- **Recall:** {metrics['recall']:.2%}\n")
        f.write(f"- **F1 Score:** {metrics['f1_score']:.2%}\n")
        f.write(f"- **Average Confidence:** {metrics['average_confidence']:.2%}\n\n")
        
        f.write("## Gate Checks\n\n")
        f.write(f"- F1 Score ≥ 0.90: {'✅ PASSED' if metrics['passed_f1_gate'] else '❌ FAILED'}\n")
        f.write(f"- False Positives on Negatives ≤ 1: {'✅ PASSED' if metrics['passed_fp_gate'] else '❌ FAILED'}\n")
        f.write(f"- **Overall:** {'✅ ALL GATES PASSED' if metrics['all_gates_passed'] else '❌ GATES FAILED'}\n\n")
        
        f.write("## Detailed Results\n\n")
        f.write("| File | Category | Detected | Correct | IoU | Confidence |\n")
        f.write("|------|----------|----------|---------|-----|------------|\n")
        
        for result in evaluation['results']:
            detected = "✓" if result['detected'] else "✗"
            correct = "✓" if result['correct'] else "✗"
            iou = f"{result['iou']:.2f}" if result['iou'] > 0 else "-"
            conf = f"{result['confidence']:.2f}" if result['confidence'] > 0 else "-"
            f.write(f"| {result['filename'][:20]} | {result['category']} | {detected} | {correct} | {iou} | {conf} |\n")
        
        f.write("\n## Confusion Matrix\n\n")
        f.write(f"- True Positives: {metrics['true_positives']}\n")
        f.write(f"- False Negatives: {metrics['false_negatives']}\n")
        f.write(f"- False Positives (partial): {metrics['false_positives_partial']}\n")
        f.write(f"- True Negatives: {metrics['true_negatives']}\n")
        f.write(f"- False Positives (on negatives): {metrics['false_positives_negative']}\n")
    
    print(f"\nReports written to:")
    print(f"  - {json_path}")
    print(f"  - {md_path}")
    
    return json_path, md_path


def main():
    parser = argparse.ArgumentParser(description='Evaluate BOM detection accuracy')
    parser.add_argument('--api-url', default='http://localhost:5000/v1/analyze',
                      help='API endpoint URL')
    parser.add_argument('--manifest', default='tests/golden/manifest.yaml',
                      help='Path to manifest file')
    parser.add_argument('--pdf-dir', default='tests/golden',
                      help='Directory containing PDF files')
    parser.add_argument('--output-dir', default='reports/detect',
                      help='Output directory for reports')
    args = parser.parse_args()
    
    # Run evaluation
    evaluation = run_evaluation(args.api_url, args.manifest, args.pdf_dir)
    
    # Write reports
    write_reports(evaluation, args.output_dir)
    
    # Print summary
    metrics = evaluation['metrics']
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Precision: {metrics['precision']:.2%}")
    print(f"Recall: {metrics['recall']:.2%}")
    print(f"F1 Score: {metrics['f1_score']:.2%}")
    print(f"Average Confidence: {metrics['average_confidence']:.2%}")
    print("-" * 60)
    
    if metrics['all_gates_passed']:
        print("✅ ALL QUALITY GATES PASSED")
        return 0
    else:
        print("❌ QUALITY GATES FAILED")
        if not metrics['passed_f1_gate']:
            print(f"  - F1 score {metrics['f1_score']:.2%} < 0.90")
        if not metrics['passed_fp_gate']:
            print(f"  - False positives on negatives: {metrics['false_positives_negative']} > 1")
        return 1


if __name__ == '__main__':
    sys.exit(main())