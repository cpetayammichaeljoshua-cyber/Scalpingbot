#!/usr/bin/env python3
"""
AI Dependency Manager - Smart Dependency Management System
Ensures PyTorch/Transformers are properly managed with intelligent alternatives
Provides runtime dependency switching and performance optimization
"""

import logging
import os
import sys
import importlib
import warnings
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import traceback

class DependencyStatus(Enum):
    """Dependency status levels"""
    AVAILABLE = "available"
    FALLBACK = "fallback"
    MISSING = "missing"
    ERROR = "error"

@dataclass
class DependencyInfo:
    """Information about a specific dependency"""
    name: str
    status: DependencyStatus
    version: Optional[str]
    alternative: Optional[str]
    performance_impact: float  # 0.0 to 1.0, where 1.0 is no impact
    error_message: Optional[str]

class AIDependencyManager:
    """
    Advanced dependency manager for AI components
    Handles PyTorch, Transformers, and other ML dependencies with intelligent fallbacks
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Core dependency configurations
        self.dependency_config = {
            'torch': {
                'required_version': '>=1.12.0',
                'alternatives': ['numpy', 'scipy'],
                'fallback_performance': 0.6,
                'critical': False,
                'installation_hint': 'pip install torch torchvision',
                'purpose': 'Deep learning and tensor operations'
            },
            'transformers': {
                'required_version': '>=4.20.0',
                'alternatives': ['sklearn', 'numpy'],
                'fallback_performance': 0.4,
                'critical': False,
                'installation_hint': 'pip install transformers',
                'purpose': 'Transformer models and NLP'
            },
            'sklearn': {
                'required_version': '>=1.0.0',
                'alternatives': ['numpy', 'scipy'],
                'fallback_performance': 0.8,
                'critical': True,
                'installation_hint': 'pip install scikit-learn',
                'purpose': 'Machine learning algorithms and preprocessing'
            },
            'numpy': {
                'required_version': '>=1.20.0',
                'alternatives': [],
                'fallback_performance': 1.0,
                'critical': True,
                'installation_hint': 'pip install numpy',
                'purpose': 'Numerical computing foundation'
            },
            'pandas': {
                'required_version': '>=1.3.0',
                'alternatives': ['numpy'],
                'fallback_performance': 0.7,
                'critical': True,
                'installation_hint': 'pip install pandas',
                'purpose': 'Data manipulation and analysis'
            },
            'scipy': {
                'required_version': '>=1.7.0',
                'alternatives': ['numpy'],
                'fallback_performance': 0.6,
                'critical': False,
                'installation_hint': 'pip install scipy',
                'purpose': 'Scientific computing and statistics'
            },
            'openai': {
                'required_version': '>=1.0.0',
                'alternatives': [],
                'fallback_performance': 0.0,
                'critical': False,
                'installation_hint': 'pip install openai',
                'purpose': 'OpenAI GPT API access',
                'requires_api_key': True
            }
        }
        
        # Dependency resolution cache
        self.dependency_cache = {}
        self.resolution_attempted = set()
        
        # Alternative method configurations
        self.alternative_methods = {
            'neural_networks': {
                'preferred': ['torch', 'transformers'],
                'alternatives': ['sklearn', 'numpy'],
                'fallback_strategy': 'statistical_ml'
            },
            'time_series_prediction': {
                'preferred': ['torch', 'scipy'],
                'alternatives': ['sklearn', 'numpy', 'pandas'],
                'fallback_strategy': 'statistical_forecasting'
            },
            'sentiment_analysis': {
                'preferred': ['transformers', 'openai'],
                'alternatives': ['sklearn', 'numpy'],
                'fallback_strategy': 'rule_based_nlp'
            },
            'pattern_recognition': {
                'preferred': ['torch', 'scipy'],
                'alternatives': ['sklearn', 'numpy'],
                'fallback_strategy': 'statistical_patterns'
            }
        }
        
    def check_all_dependencies(self) -> Dict[str, DependencyInfo]:
        """Check status of all configured dependencies"""
        self.logger.info("🔍 Checking AI dependency status...")
        
        results = {}
        for dep_name, config in self.dependency_config.items():
            results[dep_name] = self._check_single_dependency(dep_name, config)
        
        # Log summary
        self._log_dependency_summary(results)
        
        return results
    
    def _check_single_dependency(self, name: str, config: Dict[str, Any]) -> DependencyInfo:
        """Check status of a single dependency"""
        try:
            # Check if already cached
            if name in self.dependency_cache:
                return self.dependency_cache[name]
            
            # Try to import the dependency
            try:
                module = importlib.import_module(name)
                version = self._get_module_version(module, name)
                
                # Check if API key is required and available
                if config.get('requires_api_key'):
                    api_key_env = f"{name.upper()}_API_KEY"
                    if not os.environ.get(api_key_env):
                        dep_info = DependencyInfo(
                            name=name,
                            status=DependencyStatus.FALLBACK,
                            version=version,
                            alternative=None,
                            performance_impact=config.get('fallback_performance', 0.5),
                            error_message=f"API key {api_key_env} not configured"
                        )
                    else:
                        dep_info = DependencyInfo(
                            name=name,
                            status=DependencyStatus.AVAILABLE,
                            version=version,
                            alternative=None,
                            performance_impact=1.0,
                            error_message=None
                        )
                else:
                    dep_info = DependencyInfo(
                        name=name,
                        status=DependencyStatus.AVAILABLE,
                        version=version,
                        alternative=None,
                        performance_impact=1.0,
                        error_message=None
                    )
                
            except ImportError as e:
                # Module not available, check for alternatives
                alternatives = config.get('alternatives', [])
                best_alternative = self._find_best_alternative(alternatives)
                
                if best_alternative:
                    dep_info = DependencyInfo(
                        name=name,
                        status=DependencyStatus.FALLBACK,
                        version=None,
                        alternative=best_alternative,
                        performance_impact=config.get('fallback_performance', 0.5),
                        error_message=f"Using {best_alternative} as alternative"
                    )
                else:
                    dep_info = DependencyInfo(
                        name=name,
                        status=DependencyStatus.MISSING,
                        version=None,
                        alternative=None,
                        performance_impact=0.0,
                        error_message=f"Import failed: {str(e)}"
                    )
            
            # Cache the result
            self.dependency_cache[name] = dep_info
            return dep_info
            
        except Exception as e:
            self.logger.error(f"❌ Dependency check failed for {name}: {e}")
            error_info = DependencyInfo(
                name=name,
                status=DependencyStatus.ERROR,
                version=None,
                alternative=None,
                performance_impact=0.0,
                error_message=str(e)
            )
            self.dependency_cache[name] = error_info
            return error_info
    
    def _get_module_version(self, module, name: str) -> Optional[str]:
        """Get version of an imported module"""
        try:
            # Try common version attributes
            for attr in ['__version__', 'version', 'VERSION']:
                if hasattr(module, attr):
                    version = getattr(module, attr)
                    if isinstance(version, str):
                        return version
                    elif hasattr(version, '__str__'):
                        return str(version)
            
            # Try importlib metadata for newer Python versions
            try:
                import importlib.metadata
                return importlib.metadata.version(name)
            except:
                pass
                
            return "unknown"
            
        except Exception:
            return None
    
    def _find_best_alternative(self, alternatives: List[str]) -> Optional[str]:
        """Find the best available alternative from a list"""
        for alt in alternatives:
            try:
                importlib.import_module(alt)
                return alt
            except ImportError:
                continue
        return None
    
    def get_optimal_method_for_task(self, task: str) -> Dict[str, Any]:
        """Get optimal method configuration for a specific AI task"""
        if task not in self.alternative_methods:
            return {'strategy': 'unknown', 'dependencies': [], 'performance': 0.0}
        
        task_config = self.alternative_methods[task]
        preferred_deps = task_config['preferred']
        alternative_deps = task_config['alternatives']
        
        # Check availability of preferred dependencies
        available_preferred = []
        for dep in preferred_deps:
            dep_info = self._check_single_dependency(dep, self.dependency_config.get(dep, {}))
            if dep_info.status == DependencyStatus.AVAILABLE:
                available_preferred.append(dep)
        
        # If preferred dependencies are available
        if available_preferred:
            return {
                'strategy': 'preferred',
                'dependencies': available_preferred,
                'performance': 1.0,
                'method': f"Using preferred dependencies: {', '.join(available_preferred)}"
            }
        
        # Check alternative dependencies
        available_alternatives = []
        for dep in alternative_deps:
            dep_info = self._check_single_dependency(dep, self.dependency_config.get(dep, {}))
            if dep_info.status == DependencyStatus.AVAILABLE:
                available_alternatives.append(dep)
        
        if available_alternatives:
            # Calculate performance based on available alternatives
            performance = min(0.8, len(available_alternatives) / len(alternative_deps))
            return {
                'strategy': 'alternative',
                'dependencies': available_alternatives,
                'performance': performance,
                'method': f"Using alternative dependencies: {', '.join(available_alternatives)}"
            }
        
        # Fallback strategy
        return {
            'strategy': task_config['fallback_strategy'],
            'dependencies': [],
            'performance': 0.4,
            'method': f"Using fallback strategy: {task_config['fallback_strategy']}"
        }
    
    def install_missing_dependencies(self, dependencies: List[str], dry_run: bool = True) -> Dict[str, bool]:
        """Attempt to install missing dependencies (if possible)"""
        results = {}
        
        if dry_run:
            self.logger.info("🔍 Dry run: Dependencies that would be installed:")
        else:
            self.logger.info("📦 Installing missing dependencies...")
        
        for dep_name in dependencies:
            if dep_name not in self.dependency_config:
                results[dep_name] = False
                continue
            
            config = self.dependency_config[dep_name]
            install_hint = config.get('installation_hint', f'pip install {dep_name}')
            
            if dry_run:
                self.logger.info(f"   {dep_name}: {install_hint}")
                results[dep_name] = True
            else:
                # In a real implementation, this would attempt installation
                # For safety, we only provide installation hints
                self.logger.info(f"❌ Auto-installation not implemented. Please run: {install_hint}")
                results[dep_name] = False
        
        return results
    
    def get_dependency_recommendations(self) -> List[Dict[str, Any]]:
        """Get recommendations for improving dependency setup"""
        recommendations = []
        
        dep_status = self.check_all_dependencies()
        
        # Check for critical missing dependencies
        for name, info in dep_status.items():
            config = self.dependency_config[name]
            
            if info.status == DependencyStatus.MISSING and config.get('critical'):
                recommendations.append({
                    'priority': 'HIGH',
                    'type': 'missing_critical',
                    'dependency': name,
                    'message': f"Critical dependency {name} is missing",
                    'action': config.get('installation_hint'),
                    'impact': f"Reduced performance: {config.get('purpose')}"
                })
            
            elif info.status == DependencyStatus.FALLBACK:
                recommendations.append({
                    'priority': 'MEDIUM',
                    'type': 'using_fallback',
                    'dependency': name,
                    'message': f"Using fallback for {name}: {info.error_message}",
                    'action': config.get('installation_hint'),
                    'impact': f"Performance impact: {(1-info.performance_impact)*100:.0f}% reduction"
                })
        
        # Check for performance optimization opportunities
        missing_optional = [name for name, info in dep_status.items() 
                           if info.status == DependencyStatus.MISSING and 
                           not self.dependency_config[name].get('critical')]
        
        if missing_optional:
            recommendations.append({
                'priority': 'LOW',
                'type': 'optimization',
                'dependency': ', '.join(missing_optional[:3]),
                'message': f"Optional dependencies could improve performance",
                'action': "Consider installing for enhanced capabilities",
                'impact': "Potential performance improvements available"
            })
        
        return recommendations
    
    def create_dependency_report(self) -> str:
        """Create comprehensive dependency report"""
        dep_status = self.check_all_dependencies()
        recommendations = self.get_dependency_recommendations()
        
        report_lines = [
            "🔍 AI Dependency Status Report",
            "=" * 50,
            ""
        ]
        
        # Dependency status section
        report_lines.append("📊 Dependency Status:")
        for name, info in dep_status.items():
            status_emoji = {
                DependencyStatus.AVAILABLE: "✅",
                DependencyStatus.FALLBACK: "🟡",
                DependencyStatus.MISSING: "❌",
                DependencyStatus.ERROR: "🔴"
            }.get(info.status, "❓")
            
            version_info = f" (v{info.version})" if info.version else ""
            alt_info = f" -> using {info.alternative}" if info.alternative else ""
            
            report_lines.append(f"  {status_emoji} {name}{version_info}{alt_info}")
            
            if info.error_message and info.status != DependencyStatus.AVAILABLE:
                report_lines.append(f"     └─ {info.error_message}")
        
        report_lines.append("")
        
        # Performance analysis
        available_count = sum(1 for info in dep_status.values() if info.status == DependencyStatus.AVAILABLE)
        total_count = len(dep_status)
        fallback_count = sum(1 for info in dep_status.values() if info.status == DependencyStatus.FALLBACK)
        
        avg_performance = sum(info.performance_impact for info in dep_status.values()) / total_count
        
        report_lines.extend([
            "📈 Performance Analysis:",
            f"  Available: {available_count}/{total_count} ({available_count/total_count*100:.1f}%)",
            f"  Using fallbacks: {fallback_count}/{total_count}",
            f"  Average performance: {avg_performance*100:.1f}%",
            ""
        ])
        
        # Task-specific analysis
        report_lines.append("🎯 Task-Specific Capabilities:")
        for task in self.alternative_methods.keys():
            method_info = self.get_optimal_method_for_task(task)
            performance = method_info['performance'] * 100
            
            report_lines.append(f"  {task}: {performance:.0f}% - {method_info['method']}")
        
        report_lines.append("")
        
        # Recommendations section
        if recommendations:
            report_lines.append("💡 Recommendations:")
            for rec in recommendations:
                priority_emoji = {"HIGH": "🚨", "MEDIUM": "⚠️", "LOW": "💡"}.get(rec['priority'], "ℹ️")
                report_lines.append(f"  {priority_emoji} {rec['priority']}: {rec['message']}")
                if rec.get('action'):
                    report_lines.append(f"     Action: {rec['action']}")
                if rec.get('impact'):
                    report_lines.append(f"     Impact: {rec['impact']}")
                report_lines.append("")
        
        return "\n".join(report_lines)
    
    def _log_dependency_summary(self, dep_status: Dict[str, DependencyInfo]):
        """Log summary of dependency check results"""
        available = sum(1 for info in dep_status.values() if info.status == DependencyStatus.AVAILABLE)
        fallback = sum(1 for info in dep_status.values() if info.status == DependencyStatus.FALLBACK)
        missing = sum(1 for info in dep_status.values() if info.status == DependencyStatus.MISSING)
        error = sum(1 for info in dep_status.values() if info.status == DependencyStatus.ERROR)
        
        total = len(dep_status)
        
        self.logger.info(f"📊 Dependency Summary: {available}/{total} available, "
                        f"{fallback} fallbacks, {missing} missing, {error} errors")
        
        # Log critical issues
        critical_missing = [name for name, info in dep_status.items() 
                           if info.status == DependencyStatus.MISSING and 
                           self.dependency_config[name].get('critical')]
        
        if critical_missing:
            self.logger.warning(f"🚨 Critical dependencies missing: {', '.join(critical_missing)}")
        
        # Log performance impact
        avg_performance = sum(info.performance_impact for info in dep_status.values()) / total
        self.logger.info(f"📈 Overall dependency performance: {avg_performance*100:.1f}%")
    
    def optimize_imports(self) -> Dict[str, str]:
        """Provide optimized import strategies based on available dependencies"""
        dep_status = self.check_all_dependencies()
        import_strategies = {}
        
        # PyTorch optimization
        torch_info = dep_status.get('torch')
        if torch_info and torch_info.status == DependencyStatus.AVAILABLE:
            import_strategies['torch'] = "import torch; torch.set_num_threads(2)  # Optimize for Replit"
        else:
            import_strategies['torch'] = "# torch unavailable, using numpy/scipy alternatives"
        
        # Transformers optimization  
        transformers_info = dep_status.get('transformers')
        if transformers_info and transformers_info.status == DependencyStatus.AVAILABLE:
            import_strategies['transformers'] = (
                "from transformers import pipeline; "
                "import warnings; warnings.filterwarnings('ignore', category=FutureWarning)"
            )
        else:
            import_strategies['transformers'] = "# transformers unavailable, using rule-based NLP"
        
        # Scikit-learn optimization
        sklearn_info = dep_status.get('sklearn')
        if sklearn_info and sklearn_info.status == DependencyStatus.AVAILABLE:
            import_strategies['sklearn'] = "from sklearn import *; import warnings; warnings.simplefilter('ignore')"
        else:
            import_strategies['sklearn'] = "# sklearn unavailable, using numpy-based ML"
        
        return import_strategies


# Global dependency manager instance
_dependency_manager = None

def get_dependency_manager() -> AIDependencyManager:
    """Get global dependency manager instance"""
    global _dependency_manager
    if _dependency_manager is None:
        _dependency_manager = AIDependencyManager()
    return _dependency_manager

def check_ai_dependencies() -> Dict[str, DependencyInfo]:
    """Convenience function to check all AI dependencies"""
    manager = get_dependency_manager()
    return manager.check_all_dependencies()

def get_task_method(task: str) -> Dict[str, Any]:
    """Convenience function to get optimal method for a task"""
    manager = get_dependency_manager()
    return manager.get_optimal_method_for_task(task)

def create_dependency_report() -> str:
    """Convenience function to create dependency report"""
    manager = get_dependency_manager()
    return manager.create_dependency_report()