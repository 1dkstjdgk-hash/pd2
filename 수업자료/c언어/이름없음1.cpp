#include <stdio.h>
void main(){
	int i,sum,num;
	sum = 0;
	scanf("%d",&num);
	for(i=1;i<=num;i++){
		if(i%2!=0){
			sum = sum+i;
		}
		printf("%d",sum);
	}
}
