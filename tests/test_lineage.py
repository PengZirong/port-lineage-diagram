"""Run: python -m unittest discover -s tests -v"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SKILL=ROOT/'skills/port-lineage-diagram'
sys.path.insert(0,str(SKILL/'scripts'))
import lineage as L

class LineageTests(unittest.TestCase):
    def setUp(self):
        self.m=json.loads((SKILL/'assets/examples/order-checkout.json').read_text(encoding='utf-8'))
    def field(self,m,ref):
        n,f=ref.split('.')
        return next(x for x in next(x for x in m['nodes'] if x['id']==n)['fields'] if x['id']==f)
    def test_complete_coverage(self):
        r=L.validate(self.m)
        self.assertEqual(len(r['covered_outputs']),5)
        self.assertEqual(r['verified_outputs'],[])
        self.assertEqual(r['warnings'],[])
    def test_id_is_bypass_not_pricing(self):
        _,fs=L.index_model(self.m);t=L.trace(fs,'checkout.order_id')
        self.assertEqual(t['fields'],['checkout.order_id','clean.order_id','order.order_id'])
        self.assertEqual(t['roots'],['order.order_id'])
    def test_payable_excludes_order_id(self):
        _,fs=L.index_model(self.m);t=L.trace(fs,'checkout.payable_fen')
        self.assertEqual(set(t['roots']),{'order.quantity','order.unit_price_fen','order.coupon_code','order.region','coupons.amounts','rates.fees'})
        self.assertNotIn('order.order_id',t['fields'])
    def test_shipping_has_no_price_dependency(self):
        _,fs=L.index_model(self.m);t=L.trace(fs,'shipping.shipping_fen')
        self.assertEqual(set(t['roots']),{'order.region','rates.fees'})
    def test_same_name_is_not_identity(self):
        self.field(self.m,'checkout.order_id')['from']=[]
        with self.assertRaisesRegex(L.ModelError,'requires explicit from'): L.validate(self.m)
    def test_missing_field_rejected(self):
        self.field(self.m,'checkout.goods_fen')['from']=['order.missing']
        with self.assertRaisesRegex(L.ModelError,'does not exist'): L.validate(self.m)
    def test_duplicate_field_rejected(self):
        self.m['nodes'][0]['fields'].append(copy.deepcopy(self.m['nodes'][0]['fields'][0]))
        with self.assertRaisesRegex(L.ModelError,'duplicate field'): L.validate(self.m)
    def test_data_cycle_rejected(self):
        self.field(self.m,'clean.order_id')['from']=['checkout.order_id']
        with self.assertRaisesRegex(L.ModelError,'cycle'): L.validate(self.m)
    def test_control_cycle_is_not_data_cycle(self):
        self.m['controls']=[{'from':'checkout','to':'clean','label':'仅失败时重试','loop':True}]
        self.assertTrue(L.validate(self.m)['valid'])
    def test_passthrough_type_change_rejected(self):
        self.field(self.m,'checkout.order_id')['type']='int'
        with self.assertRaisesRegex(L.ModelError,'preserve type'): L.validate(self.m)
    def test_unknown_cannot_count_as_covered(self):
        self.m['nodes'][-1]['fields'].append(dict(id='audit_tag',label='审计标记',type='str',op='unknown',note='提供的材料没有来源'))
        self.m['outputs'].append('checkout.audit_tag')
        r=L.validate(self.m)
        self.assertEqual(len(r['covered_outputs']),5)
        self.assertEqual(len(r['outputs']),6)
        self.assertEqual(r['traces']['checkout.audit_tag']['unknown'],['checkout.audit_tag'])
    def test_verified_requires_evidence_and_grounding(self):
        self.field(self.m,'checkout.order_id')['status']='verified'
        with self.assertRaisesRegex(L.ModelError,'verified'): L.validate(self.m)
    def test_selector_is_not_a_copied_value(self):
        _,fs=L.index_model(self.m)
        d=L.dependencies(fs['pricing.coupon_fen'])
        self.assertEqual([x for x in d if x['role']=='selector'][0]['ref'],'clean.coupon_code')
        self.field(self.m,'checkout.order_id')['from']=[{'ref':'clean.order_id','role':'selector'}]
        with self.assertRaisesRegex(L.ModelError,'value dependency'): L.validate(self.m)
    def test_choose_requires_conditions(self):
        f=self.field(self.m,'checkout.payable_fen');f['op']='choose'
        with self.assertRaisesRegex(L.ModelError,'guarded'): L.validate(self.m)
    def test_root_constant_and_runtime_are_legal(self):
        f=self.field(self.m,'coupons.amounts');f['origin']['kind']='constant'
        f=self.field(self.m,'rates.fees');f['origin']['kind']='runtime'
        self.assertTrue(L.validate(self.m)['valid'])
    def test_no_partially_hardcoded_layout(self):
        del self.m['nodes'][0]['position']
        with self.assertRaisesRegex(L.ModelError,'all nodes or none'): L.validate(self.m)
    def test_overlap_is_rejected(self):
        self.m['nodes'][1]['position']=self.m['nodes'][0]['position']
        boxes=L.layout(self.m)
        self.assertTrue(L.geometry_issues(boxes))
    def test_example_rule_arithmetic(self):
        # Test this illustrative rule only; never eval rules supplied in a model.
        goods=int('2')*10000;coupon={'SAVE20':2000}.get('save20'.upper(),0);fee={'east':800}['east']
        self.assertEqual(max(goods-coupon,0)+fee,18800)
        self.assertEqual(max(1500-2000,0)+800,800)
        self.assertEqual({'SAVE20':2000}.get('UNKNOWN',0),0)
    def test_generic_second_example_auto_layout(self):
        m=json.loads((SKILL/'assets/examples/file-import.json').read_text(encoding='utf-8'))
        r=L.validate(m);b=L.layout(m)
        self.assertEqual(len(r['covered_outputs']),3)
        self.assertEqual(L.geometry_issues(b),[])
        svg,_=L.render_svg(m,r,b)
        self.assertIn('received_at',svg)
        self.assertNotIn('payable_fen',svg)
    def test_injection_is_data_not_executable_html(self):
        self.m['title']='safe </script><img src=x onerror=alert(1)>'
        self.field(self.m,'checkout.order_id')['label']='<b>not markup</b>'
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'m.json';p.write_text(json.dumps(self.m),encoding='utf-8')
            L.build(p,Path(t)/'out')
            page=(Path(t)/'out/index.html').read_text()
            self.assertNotIn('<img src=x onerror=alert(1)>',page)
            self.assertNotIn('<b>not markup</b>',page)
            self.assertIn('\\u003c/script\\u003e',page)
    def test_safe_route_coordinates(self):
        self.m['routes']={'a->b':[['"><script>',10]]}
        with self.assertRaisesRegex(L.ModelError,'waypoints'): L.validate(self.m)
    def test_build_is_deterministic_and_offline(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=Path(t)/'a',Path(t)/'b'
            L.build(SKILL/'assets/examples/order-checkout.json',a,True)
            L.build(SKILL/'assets/examples/order-checkout.json',b,True)
            for name in ('index.html','diagram.svg','model.json','validation.json'):
                self.assertEqual((a/name).read_bytes(),(b/name).read_bytes())
            h=(a/'index.html').read_text()
            self.assertNotIn('<script src=',h);self.assertNotIn('fonts.googleapis.com',h)
if __name__=='__main__':unittest.main()
