#!/usr/bin/env python3
"""
Threshold Calibration Tool
Sweeps confidence thresholds to find optimal value
"""

import os
import sys
import json
import yaml
import argparse
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple

# Import evaluation functions
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_detect import calculate_iou, evaluate_detection, calculate_metrics


def sweep_thresholds(results_file: str, manifest_file: str, 
                     min_threshold: float = 0.50, 
                     max_threshold: float = 0.95,
                     step: float = 0.05) -> List[Dict]:
    """
    Sweep confidence thresholds and calculate metrics for each.
    """
    # Load pre-computed detection results
    with open(results_file, 'r') as f:
        all_results = json.load(f)
    
    # Load manifest
    with open(manifest_file, 'r') as f:
        manifest = yaml.safe_load(f)
    
    threshold_results = []
    thresholds = np.arange(min_threshold, max_threshold + step, step)
    
    print(f"Sweeping thresholds from {min_threshold:.2f} to {max_threshold:.2f}")
    print("-" * 60)
    print(f"{'Threshold':>10} | {'Precision':>10} | {'Recall':>10} | {'F1 Score':>10} | {'FP on Neg':>10}")
    print("-" * 60)
    
    for threshold in thresholds:
        # Filter detections by threshold
        filtered_results = []
        
        for result in all_results['results']:
            # Apply threshold filtering
            filtered_result = result.copy()
            if 'detection' in result and result['detection']:
                detections = result['detection'].get('detections', [])
                # Filter detections by confidence
                filtered_detections = [d for d in detections if d.get('confidence', 0) >= threshold]
                filtered_result['detection']['detections'] = filtered_detections
            
            # Re-evaluate with filtered detections
            ground_truth = next((f for f in manifest['files'] if f['filename'] == result['filename']), None)
            if ground_truth:
                eval_result = evaluate_detection(filtered_result.get('detection'), ground_truth)
                filtered_results.append(eval_result)
        
        # Calculate metrics
        metrics = calculate_metrics(filtered_results, manifest['evaluation'])
        
        threshold_result = {
            'threshold': threshold,
            'precision': metrics['precision'],
            'recall': metrics['recall'],
            'f1_score': metrics['f1_score'],
            'false_positives_negative': metrics['false_positives_negative']
        }
        threshold_results.append(threshold_result)
        
        # Print row
        print(f"{threshold:10.2f} | {metrics['precision']:10.2%} | {metrics['recall']:10.2%} | "
              f"{metrics['f1_score']:10.2%} | {metrics['false_positives_negative']:10d}")
    
    print("-" * 60)
    
    return threshold_results


def find_optimal_threshold(threshold_results: List[Dict]) -> Tuple[float, Dict]:
    """
    Find the optimal threshold based on F1 score and false positive constraints.
    """
    # Filter by false positive constraint first
    valid_results = [r for r in threshold_results if r['false_positives_negative'] <= 1]
    
    if not valid_results:
        # If no threshold meets FP constraint, pick the one with lowest FP
        min_fp = min(r['false_positives_negative'] for r in threshold_results)
        valid_results = [r for r in threshold_results if r['false_positives_negative'] == min_fp]
    
    # Among valid results, pick the one with highest F1 score
    optimal = max(valid_results, key=lambda x: x['f1_score'])
    
    return optimal['threshold'], optimal


def plot_ascii_chart(threshold_results: List[Dict]):
    """
    Create an ASCII chart of the results.
    """
    print("\nThreshold vs Metrics (ASCII Chart)")
    print("=" * 70)
    
    # Scale values to 0-20 for ASCII display
    max_height = 20
    
    for metric_name in ['precision', 'recall', 'f1_score']:
        print(f"\n{metric_name.upper()}")
        print("-" * 70)
        
        for i, result in enumerate(threshold_results):
            threshold = result['threshold']
            value = result[metric_name]
            bar_height = int(value * max_height)
            bar = '█' * bar_height + '░' * (max_height - bar_height)
            print(f"{threshold:.2f} |{bar}| {value:.2%}")
    
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='Calibrate confidence threshold')
    parser.add_argument('--results', help='Pre-computed detection results JSON')
    parser.add_argument('--manifest', default='tests/golden/manifest.yaml',
                      help='Path to manifest file')
    parser.add_argument('--min-threshold', type=float, default=0.50,
                      help='Minimum threshold to test')
    parser.add_argument('--max-threshold', type=float, default=0.95,
                      help='Maximum threshold to test')
    parser.add_argument('--step', type=float, default=0.05,
                      help='Threshold step size')
    parser.add_argument('--output', help='Output JSON file for results')
    
    args = parser.parse_args()
    
    # If no results file provided, inform user to run evaluation first
    if not args.results:
        print("ERROR: No results file provided.")
        print("Please run evaluation first to generate detection results:")
        print("  python tools/eval_detect.py")
        print("Then use the generated JSON file with --results parameter")
        return 1
    
    if not os.path.exists(args.results):
        print(f"ERROR: Results file not found: {args.results}")
        return 1
    
    # Sweep thresholds
    threshold_results = sweep_thresholds(
        args.results, 
        args.manifest,
        args.min_threshold,
        args.max_threshold,
        args.step
    )
    
    # Find optimal threshold
    optimal_threshold, optimal_metrics = find_optimal_threshold(threshold_results)
    
    print("\n" + "=" * 60)
    print("OPTIMAL THRESHOLD ANALYSIS")
    print("=" * 60)
    print(f"Recommended Threshold: {optimal_threshold:.2f}")
    print(f"Precision: {optimal_metrics['precision']:.2%}")
    print(f"Recall: {optimal_metrics['recall']:.2%}")
    print(f"F1 Score: {optimal_metrics['f1_score']:.2%}")
    print(f"False Positives on Negatives: {optimal_metrics['false_positives_negative']}")
    print("=" * 60)
    
    # Plot ASCII chart
    plot_ascii_chart(threshold_results)
    
    # Save results if output specified
    if args.output:
        output_data = {
            'threshold_sweep': threshold_results,
            'optimal_threshold': optimal_threshold,
            'optimal_metrics': optimal_metrics
        }
        with open(args.output, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to: {args.output}")
    
    # Recommendation
    print("\nRECOMMENDATION:")
    print("-" * 60)
    if optimal_threshold != 0.70:
        print(f"Consider updating CONFIDENCE_THRESHOLD from 0.70 to {optimal_threshold:.2f}")
        print("This can be done in the configuration or as an environment variable.")
    else:
        print("Current default threshold of 0.70 appears to be optimal.")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())