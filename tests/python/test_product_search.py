import copy
import unittest
from architecture_search import product_search, products


class ProductAcquisition(unittest.TestCase):
    def test_future_hardware_measurements_cannot_change_selection(self):
        w=products.workload();pool=[{'configuration':c} for c in products.candidates(w)]
        selected,prediction=product_search.choose(w,pool,[],'cost',3,2)
        hidden=copy.deepcopy(pool)
        for i,r in enumerate(hidden):r['evidence']={'synthesis':{'implementation_passed':True,'metrics':{'lut':i+1}}}
        actual,estimate=product_search.choose(w,hidden,[],'cost',3,2)
        self.assertEqual(selected['configuration'],actual['configuration'])
        self.assertEqual(prediction,estimate)

    def test_models_do_not_mix_generators(self):
        w=products.workload();cs=products.candidates(w)
        fft={'configuration':next(c for c in cs if c['generator']=='sgen')}
        ntt={'configuration':next(c for c in cs if c['generator']=='ngen'),
             'evidence':{'synthesis':{'implementation_passed':True,'metrics':{'lut':1}}}}
        estimate=product_search.estimate(w,fft,[ntt],learned=True)
        self.assertEqual(estimate['samples'],0)
        fft['evidence']={'synthesis':{'implementation_passed':True,'metrics':{'lut':123}}}
        self.assertEqual(product_search.estimate(w,fft,[fft,ntt],learned=True)['lut'],123)

    def test_reproducible_policies_and_exploration(self):
        w=products.workload();pool=[{'configuration':c} for c in products.candidates(w)]
        for policy in ('enumerate','random','analytical','cost'):
            for step in range(4):
                self.assertEqual(product_search.choose(w,pool,[],policy,7,step),
                                 product_search.choose(w,list(reversed(pool)),[],policy,7,step))
        self.assertEqual(product_search.choose(w,pool,[],'cost',7,3)[1]['method'],'seeded-exploration')


if __name__=='__main__':unittest.main()
